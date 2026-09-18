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
"""

from __future__ import annotations

import heapq
import weakref
from collections import OrderedDict
from typing import Callable, Dict, Hashable, Iterable, List, Optional, Set, Tuple

__all__ = ["Group", "TitoError", "TitoQueue"]


class TitoError(Exception):
    """Raised when an operation would violate the TITO invariants."""


class Group:
    """A set of members that entered the queue together.

    A group is only ever released as a whole: it departs when, and only
    when, all of its members have been marked ready.
    """

    __slots__ = ("group_id", "_members", "_member_set", "_ready", "sequence", "_on_ready")

    def __init__(self, group_id: Hashable, members: Iterable[Hashable], sequence: int) -> None:
        member_list: Tuple[Hashable, ...] = tuple(members)
        if not member_list:
            raise TitoError(f"group {group_id!r} must contain at least one member")
        member_set = set(member_list)
        if len(member_set) != len(member_list):
            raise TitoError(f"group {group_id!r} contains duplicate members")
        self.group_id = group_id
        self._members = member_list
        self._member_set = member_set
        self._ready: Set[Hashable] = set()
        self.sequence = sequence
        self._on_ready: Optional[Callable[["Group"], None]] = None

    @property
    def members(self) -> Tuple[Hashable, ...]:
        """The members of this group, in the order they were admitted."""
        return self._members

    @property
    def ready_members(self) -> Tuple[Hashable, ...]:
        """Members already marked ready, in admission order."""
        return tuple(m for m in self._members if m in self._ready)

    @property
    def waiting_members(self) -> Tuple[Hashable, ...]:
        """Members not yet marked ready, in admission order."""
        return tuple(m for m in self._members if m not in self._ready)

    @property
    def is_ready(self) -> bool:
        """True once every member of the group is ready to depart."""
        return len(self._ready) == len(self._members)

    def mark_ready(self, member: Hashable) -> bool:
        """Mark ``member`` ready. Returns True if the whole group is ready."""
        if member not in self._member_set:
            raise TitoError(f"{member!r} is not a member of group {self.group_id!r}")
        was_ready = self.is_ready
        self._ready.add(member)
        if not self.is_ready:
            return False
        if not was_ready and self._on_ready is not None:
            self._on_ready(self)
        return True

    def __len__(self) -> int:
        return len(self._members)

    def __iter__(self):
        return iter(self._members)

    def __contains__(self, member: Hashable) -> bool:
        return member in self._member_set

    def __repr__(self) -> str:
        return (
            f"Group(group_id={self.group_id!r}, members={list(self._members)!r}, "
            f"ready={len(self._ready)}/{len(self._members)})"
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

    def __init__(self, strict_order: bool = True) -> None:
        self.strict_order = strict_order
        self._groups: "OrderedDict[Hashable, Group]" = OrderedDict()
        self._member_index: Dict[Hashable, Hashable] = {}
        self._sequence = 0
        self._ready_heap: List[int] = []
        self._ready_seqs: Set[int] = set()
        self._ready_groups: Dict[int, Group] = {}
        # Groups hold this callback, so it must not hold a strong reference
        # back to the queue: that cycle would keep released queues (and every
        # group still in them) alive until the cyclic collector runs.
        self._on_ready_callback = _make_ready_callback(self)

    def admit(self, group_id: Hashable, members: Iterable[Hashable]) -> Group:
        """Admit ``members`` as a single group. All of them enter together."""
        if group_id in self._groups:
            raise TitoError(f"group {group_id!r} is already in the queue")
        group = Group(group_id, members, self._sequence)
        already_queued = [m for m in group.members if m in self._member_index]
        if already_queued:
            raise TitoError(f"members already in the queue: {already_queued!r}")
        self._sequence += 1
        self._groups[group_id] = group
        for member in group.members:
            self._member_index[member] = group_id
        group._on_ready = self._on_ready_callback
        return group

    def mark_ready(self, member: Hashable) -> bool:
        """Mark a queued ``member`` ready. Returns True if its group is ready."""
        group = self.group_of(member)
        if group is None:
            raise TitoError(f"{member!r} is not in the queue")
        return group.mark_ready(member)

    def mark_group_ready(self, group_id: Hashable) -> bool:
        """Mark every member of ``group_id`` ready."""
        group = self._groups.get(group_id)
        if group is None:
            raise TitoError(f"group {group_id!r} is not in the queue")
        for member in group.members:
            group.mark_ready(member)
        return True

    def group_of(self, member: Hashable) -> Optional[Group]:
        """The group a queued ``member`` belongs to, or None if not queued."""
        if member not in self._member_index:
            return None
        group_id = self._member_index[member]
        return self._groups[group_id]

    def cancel(self, group_id: Hashable) -> Group:
        """Withdraw a waiting group from the queue and return it.

        The whole group leaves together, ready or not: cancelling is the only
        way a group departs without every member being ready.
        """
        group = self._groups.get(group_id)
        if group is None:
            raise TitoError(f"group {group_id!r} is not in the queue")
        self._remove(group)
        return group

    def clear(self) -> List[Group]:
        """Withdraw every waiting group, in arrival order, and return them."""
        cleared = list(self._groups.values())
        for group in cleared:
            group._on_ready = None
        self._groups.clear()
        self._member_index.clear()
        self._ready_seqs.clear()
        self._ready_groups.clear()
        self._ready_heap.clear()
        return cleared

    def peek(self) -> Optional[Group]:
        """The next group that would be released, without releasing it."""
        if self.strict_order:
            head = next(iter(self._groups.values()), None)
            if head is None or not head.is_ready:
                return None
            return head
        while self._ready_heap:
            sequence = self._ready_heap[0]
            if sequence in self._ready_seqs:
                return self._ready_groups[sequence]
            heapq.heappop(self._ready_heap)
        return None

    def release(self) -> Optional[Group]:
        """Release the next fully ready group, or None if none can depart."""
        group = self.peek()
        if group is None:
            return None
        self._remove(group)
        return group

    def release_all(self) -> List[Group]:
        """Release every group that can currently depart, in order."""
        released: List[Group] = []
        while True:
            group = self.release()
            if group is None:
                return released
            released.append(group)

    def _note_ready(self, group: Group) -> None:
        """Record that ``group`` became ready, keeping arrival order."""
        sequence = group.sequence
        if sequence in self._ready_seqs:
            return
        self._ready_seqs.add(sequence)
        self._ready_groups[sequence] = group
        heapq.heappush(self._ready_heap, sequence)

    def _remove(self, group: Group) -> None:
        del self._groups[group.group_id]
        for member in group.members:
            del self._member_index[member]
        group._on_ready = None
        self._ready_seqs.discard(group.sequence)
        self._ready_groups.pop(group.sequence, None)
        self._compact_ready_heap()

    def _compact_ready_heap(self) -> None:
        """Drop stale sequences so the ready heap cannot grow without bound.

        ``peek`` only discards stale entries once they reach the top of the
        heap, and in strict-order mode it never touches the heap at all, so
        departed groups would otherwise leave their sequence numbers behind
        forever.
        """
        if len(self._ready_heap) <= 2 * len(self._ready_seqs) + 8:
            return
        self._ready_heap = list(self._ready_seqs)
        heapq.heapify(self._ready_heap)

    @property
    def groups(self) -> Tuple[Group, ...]:
        """Waiting groups, in arrival order."""
        return tuple(self._groups.values())

    def __len__(self) -> int:
        """Number of waiting groups."""
        return len(self._groups)

    def __contains__(self, member: Hashable) -> bool:
        return member in self._member_index

    def __repr__(self) -> str:
        return f"TitoQueue(strict_order={self.strict_order}, groups={len(self._groups)})"
