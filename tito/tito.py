"""Together In Together Out (TITO).

TITO is a batch scheduling discipline: members that enter the system as a
group are never split up while they wait, and they only leave the system
once *every* member of their group is ready to leave.

Two ordering policies are supported:

``strict_order=True`` (default)
    Head-of-line FIFO. Only the oldest waiting group may depart, so a group
    that becomes ready early still waits for the groups that arrived before
    it. This guarantees groups exit in exactly their arrival order.

``strict_order=False``
    Any fully ready group may depart. Ready groups are still released in
    arrival order relative to one another, but a group that is not ready
    does not block younger groups behind it.

Both :class:`TitoQueue` and :class:`Group` are thread-safe. A queue and the
groups it has admitted share one reentrant lock, so marking a member ready
and the queue bookkeeping it triggers happen as a single atomic step, and no
group can be released twice by racing callers.
"""

from __future__ import annotations

import heapq
import threading
import weakref
from collections import OrderedDict
from typing import Callable, Dict, Hashable, Iterable, Iterator, List, Optional, Tuple

__all__ = ["Group", "TitoError", "TitoQueue"]


class TitoError(Exception):
    """Raised when an operation would violate the TITO invariants."""


class Group:
    """A set of members that entered the queue together.

    A group is only ever released as a whole: it departs when, and only
    when, all of its members have been marked ready.
    """

    __slots__ = (
        "group_id",
        "_members",
        "_ready",
        "_ready_count",
        "_sequence",
        "_on_ready",
        "_lock",
    )

    def __init__(self, group_id: Hashable, members: Iterable[Hashable], sequence: int) -> None:
        member_list: Tuple[Hashable, ...] = tuple(members)
        if not member_list:
            raise TitoError(f"group {group_id!r} must contain at least one member")
        # One dict replaces the former "all members" set plus "ready members"
        # set: it answers membership in O(1) and carries the ready flag in the
        # same slot, so a fully ready group no longer stores every member twice.
        ready: Dict[Hashable, bool] = dict.fromkeys(member_list, False)
        if len(ready) != len(member_list):
            raise TitoError(f"group {group_id!r} contains duplicate members")
        self.group_id = group_id
        self._members = member_list
        self._ready = ready
        self._ready_count = 0
        self._sequence = sequence
        self._on_ready: Optional[Callable[["Group"], None]] = None
        # Reentrant because the readiness callback re-enters the queue, which
        # shares this very lock once the group has been admitted.
        self._lock: "threading.RLock" = threading.RLock()

    @property
    def sequence(self) -> int:
        """Arrival order of this group. Read-only: the queue indexes on it."""
        return self._sequence

    @property
    def members(self) -> Tuple[Hashable, ...]:
        """The members of this group, in the order they were admitted."""
        return self._members

    @property
    def ready_members(self) -> Tuple[Hashable, ...]:
        """Members already marked ready, in admission order."""
        with self._lock:
            ready = self._ready
            return tuple(m for m in self._members if ready[m])

    @property
    def waiting_members(self) -> Tuple[Hashable, ...]:
        """Members not yet marked ready, in admission order."""
        with self._lock:
            ready = self._ready
            return tuple(m for m in self._members if not ready[m])

    @property
    def ready_count(self) -> int:
        """How many members have been marked ready."""
        with self._lock:
            return self._ready_count

    @property
    def is_ready(self) -> bool:
        """True once every member of the group is ready to depart."""
        with self._lock:
            return self._ready_count == len(self._members)

    def mark_ready(self, member: Hashable) -> bool:
        """Mark ``member`` ready. Returns True if the whole group is ready.

        Exactly one caller sees the group complete: concurrent callers that
        arrive afterwards still get True, but the queue is notified once.
        """
        with self._lock:
            try:
                already = self._ready[member]
            except KeyError:
                raise TitoError(
                    f"{member!r} is not a member of group {self.group_id!r}"
                ) from None
            except TypeError:
                raise TitoError(
                    f"{member!r} is not a member of group {self.group_id!r}"
                ) from None
            if already:
                return self._ready_count == len(self._members)
            self._ready[member] = True
            self._ready_count += 1
            if self._ready_count != len(self._members):
                return False
            if self._on_ready is not None:
                self._on_ready(self)
            return True

    def __len__(self) -> int:
        return len(self._members)

    def __iter__(self) -> Iterator[Hashable]:
        return iter(self._members)

    def __contains__(self, member: Hashable) -> bool:
        try:
            return member in self._ready
        except TypeError:
            return False

    def __repr__(self) -> str:
        with self._lock:
            ready_count = self._ready_count
        return (
            f"Group(group_id={self.group_id!r}, members={list(self._members)!r}, "
            f"ready={ready_count}/{len(self._members)})"
        )


def _make_ready_callback(queue: "TitoQueue") -> Callable[["Group"], None]:
    """Build a group callback that only weakly references ``queue``."""
    queue_ref = weakref.ref(queue)

    def on_ready(group: "Group") -> None:
        owner = queue_ref()
        if owner is not None:
            owner._note_ready(group)

    return on_ready


class TitoQueue:
    """A queue that admits and releases members group-by-group."""

    __slots__ = (
        "_strict_order",
        "_groups",
        "_member_index",
        "_sequence",
        "_ready_heap",
        "_ready_groups",
        "_on_ready_callback",
        "_lock",
        "__weakref__",
    )

    def __init__(self, strict_order: bool = True) -> None:
        self._strict_order = bool(strict_order)
        # Reentrant: ``release`` calls ``peek``, and a group notifying the
        # queue that it became ready already holds this same lock.
        self._lock = threading.RLock()
        self._groups: "OrderedDict[Hashable, Group]" = OrderedDict()
        self._member_index: Dict[Hashable, Hashable] = {}
        self._sequence = 0
        # Only the non-strict policy needs a ready index: strict order always
        # releases the head of the queue, so tracking which younger groups are
        # ready would cost time and memory for information never read.
        self._ready_heap: List[int] = []
        self._ready_groups: Dict[int, Group] = {}
        # Groups hold this callback, so it must not hold a strong reference
        # back to the queue: that cycle would keep released queues (and every
        # group still in them) alive until the cyclic collector runs.
        self._on_ready_callback: Optional[Callable[[Group], None]] = (
            None if self._strict_order else _make_ready_callback(self)
        )

    @property
    def strict_order(self) -> bool:
        """The ordering policy. Read-only: it selects the indexing strategy."""
        return self._strict_order

    def admit(self, group_id: Hashable, members: Iterable[Hashable]) -> Group:
        """Admit ``members`` as a single group. All of them enter together."""
        # Built outside the lock: validating members can run arbitrary user
        # code (hashing, iterating the ``members`` argument).
        group = Group(group_id, members, 0)
        with self._lock:
            if group_id in self._groups:
                raise TitoError(f"group {group_id!r} is already in the queue")
            member_index = self._member_index
            already_queued = [m for m in group.members if m in member_index]
            if already_queued:
                raise TitoError(f"members already in the queue: {already_queued!r}")
            group._sequence = self._sequence
            self._sequence += 1
            # The group shares the queue lock from now on, so marking a member
            # ready and the queue bookkeeping it triggers are one atomic step.
            # The group is still unpublished here, so no other thread can hold
            # its old lock while we swap it.
            group._lock = self._lock
            self._groups[group_id] = group
            for member in group.members:
                member_index[member] = group_id
            group._on_ready = self._on_ready_callback
            return group

    def mark_ready(self, member: Hashable) -> bool:
        """Mark a queued ``member`` ready. Returns True if its group is ready."""
        with self._lock:
            group = self.group_of(member)
            if group is None:
                raise TitoError(f"{member!r} is not in the queue")
            return group.mark_ready(member)

    def mark_group_ready(self, group_id: Hashable) -> bool:
        """Mark every member of ``group_id`` ready."""
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise TitoError(f"group {group_id!r} is not in the queue")
            for member in group.members:
                group.mark_ready(member)
            return True

    def group_of(self, member: Hashable) -> Optional[Group]:
        """The group a queued ``member`` belongs to, or None if not queued."""
        with self._lock:
            try:
                group_id = self._member_index[member]
            except KeyError:
                return None
            except TypeError:
                return None
            return self._groups[group_id]

    def cancel(self, group_id: Hashable) -> Group:
        """Withdraw a waiting group from the queue and return it.

        The whole group leaves together, ready or not: cancelling is the only
        way a group departs without every member being ready.
        """
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise TitoError(f"group {group_id!r} is not in the queue")
            self._remove(group)
            return group

    def clear(self) -> List[Group]:
        """Withdraw every waiting group, in arrival order, and return them."""
        with self._lock:
            cleared = list(self._groups.values())
            for group in cleared:
                group._on_ready = None
            self._groups.clear()
            self._member_index.clear()
            self._ready_groups.clear()
            self._ready_heap.clear()
            return cleared

    def peek(self) -> Optional[Group]:
        """The next group that would be released, without releasing it."""
        with self._lock:
            if self._strict_order:
                head = next(iter(self._groups.values()), None)
                if head is None or not head.is_ready:
                    return None
                return head
            heap = self._ready_heap
            ready_groups = self._ready_groups
            while heap:
                group = ready_groups.get(heap[0])
                if group is not None:
                    return group
                heapq.heappop(heap)
            return None

    def release(self) -> Optional[Group]:
        """Release the next fully ready group, or None if none can depart."""
        with self._lock:
            group = self.peek()
            if group is None:
                return None
            self._remove(group)
            return group

    def release_all(self) -> List[Group]:
        """Release every group that can currently depart, in order."""
        released: List[Group] = []
        with self._lock:
            while True:
                group = self.release()
                if group is None:
                    return released
                released.append(group)

    def _note_ready(self, group: Group) -> None:
        """Record that ``group`` became ready, keeping arrival order."""
        sequence = group.sequence
        if sequence in self._ready_groups:
            return
        self._ready_groups[sequence] = group
        heapq.heappush(self._ready_heap, sequence)

    def _remove(self, group: Group) -> None:
        del self._groups[group.group_id]
        member_index = self._member_index
        for member in group.members:
            del member_index[member]
        group._on_ready = None
        if self._ready_groups.pop(group.sequence, None) is not None:
            self._compact_ready_heap()

    def _compact_ready_heap(self) -> None:
        """Drop stale sequences so the ready heap cannot grow without bound.

        ``peek`` only discards stale entries once they reach the top of the
        heap, so departed groups would otherwise leave their sequence numbers
        behind forever.
        """
        if len(self._ready_heap) <= 2 * len(self._ready_groups) + 8:
            return
        self._ready_heap = list(self._ready_groups)
        heapq.heapify(self._ready_heap)

    @property
    def groups(self) -> Tuple[Group, ...]:
        """Waiting groups, in arrival order."""
        with self._lock:
            return tuple(self._groups.values())

    def __len__(self) -> int:
        """Number of waiting groups."""
        return len(self._groups)

    def __contains__(self, member: Hashable) -> bool:
        try:
            return member in self._member_index
        except TypeError:
            return False

    def __repr__(self) -> str:
        return f"TitoQueue(strict_order={self._strict_order}, groups={len(self._groups)})"
