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
group can be released twice by racing callers. Consumers can sleep in
``release(block=True)`` until a group is able to depart instead of polling.
"""

from __future__ import annotations

import heapq
import threading
import time
import weakref
from collections import OrderedDict
from typing import Callable, Dict, Hashable, Iterable, Iterator, List, Optional, Tuple

__all__ = ["Group", "TitoError", "TitoQueue"]


class TitoError(Exception):
    """Raised when an operation would violate the TITO invariants."""


def _is_hashable(value: object) -> bool:
    """Whether ``value`` can be used as a group id or member."""
    try:
        hash(value)
    except TypeError:
        return False
    return True


def _check_wait(block: bool, timeout: Optional[float]) -> None:
    """Refuse a ``timeout`` that would be ignored, or that cannot be waited."""
    if timeout is None:
        return
    if not block:
        raise TitoError(
            f"timeout={timeout!r} only applies when waiting; pass block=True "
            f"as well, or drop the timeout to return straight away"
        )
    try:
        valid = timeout >= 0
    except TypeError:
        valid = False
    if not valid:
        raise TitoError(
            f"timeout must be None or a non-negative number of seconds, "
            f"not {timeout!r}"
        )


class Group:
    """A set of members that entered the queue together.

    A group is only ever released as a whole: it departs when, and only
    when, all of its members are marked ready.
    """

    __slots__ = (
        "group_id",
        "_members",
        "_ready",
        "_ready_count",
        "_sequence",
        "_on_change",
        "_lock",
    )

    def __init__(self, group_id: Hashable, members: Iterable[Hashable], sequence: int) -> None:
        # A bare string iterates character by character, which is never what a
        # caller means by "the members of this group", so say so plainly
        # instead of admitting one group per letter.
        if isinstance(members, (str, bytes)):
            raise TitoError(
                f"group {group_id!r} was given {members!r} as its members; "
                f"pass a collection such as [{members!r}] instead"
            )
        member_list: Tuple[Hashable, ...] = tuple(members)
        if not member_list:
            raise TitoError(f"group {group_id!r} must contain at least one member")
        # One dict replaces the former "all members" set plus "ready members"
        # set: it answers membership in O(1) and carries the ready flag in the
        # same slot, so a fully ready group no longer stores every member twice.
        try:
            ready: Dict[Hashable, bool] = dict.fromkeys(member_list, False)
        except TypeError:
            unhashable = [m for m in member_list if not _is_hashable(m)]
            raise TitoError(
                f"group {group_id!r} contains unhashable members: {unhashable!r}"
            ) from None
        if len(ready) != len(member_list):
            seen: Dict[Hashable, bool] = {}
            duplicates: List[Hashable] = []
            for member in member_list:
                if member in seen and member not in duplicates:
                    duplicates.append(member)
                seen[member] = True
            raise TitoError(
                f"group {group_id!r} contains duplicate members: {duplicates!r}"
            )
        self.group_id = group_id
        self._members = member_list
        self._ready = ready
        self._ready_count = 0
        self._sequence = sequence
        # Called with (group, is_ready) whenever the whole group becomes ready
        # or stops being ready, so the queue holding it can keep up.
        self._on_change: Optional[Callable[["Group", bool], None]] = None
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
            if self._member_is_ready(member):
                return self._ready_count == len(self._members)
            self._ready[member] = True
            self._ready_count += 1
            if self._ready_count != len(self._members):
                return False
            if self._on_change is not None:
                self._on_change(self, True)
            return True

    def mark_waiting(self, member: Hashable) -> None:
        """Mark ``member`` as not ready after all, so the group cannot depart.

        The group stays whole and keeps its place in the queue; it can only
        depart once ``member`` is marked ready again. Marking a member that
        is already waiting does nothing.
        """
        with self._lock:
            if not self._member_is_ready(member):
                return
            was_ready = self._ready_count == len(self._members)
            self._ready[member] = False
            self._ready_count -= 1
            if was_ready and self._on_change is not None:
                self._on_change(self, False)

    def _member_is_ready(self, member: Hashable) -> bool:
        """Whether ``member`` is marked ready; refuses anyone not in the group."""
        try:
            return self._ready[member]
        except (KeyError, TypeError):
            raise TitoError(
                f"{member!r} is not a member of group {self.group_id!r}; "
                f"its members are {list(self._members)!r}"
            ) from None

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
            waiting = self.waiting_members
        waiting_note = f", waiting on {list(waiting)!r}" if waiting else ""
        return (
            f"Group(group_id={self.group_id!r}, members={list(self._members)!r}, "
            f"ready={ready_count}/{len(self._members)}{waiting_note})"
        )


def _make_change_callback(queue: "TitoQueue") -> Callable[["Group", bool], None]:
    """Build a group callback that only weakly references ``queue``."""
    queue_ref = weakref.ref(queue)

    def on_change(group: "Group", ready: bool) -> None:
        owner = queue_ref()
        if owner is not None:
            owner._note_change(group, ready)

    return on_change


class TitoQueue:
    """A queue that admits and releases members group-by-group."""

    __slots__ = (
        "_strict_order",
        "_groups",
        "_member_index",
        "_sequence",
        "_ready_heap",
        "_ready_groups",
        "_on_change_callback",
        "_lock",
        "_departure",
        "_blocked",
        "__weakref__",
    )

    def __init__(self, strict_order: bool = True) -> None:
        self._strict_order = bool(strict_order)
        # Reentrant: ``release`` calls ``peek``, and a group notifying the
        # queue that it became ready already holds this same lock.
        self._lock = threading.RLock()
        # Consumers blocked in ``release(block=True)`` sleep on this until a
        # group can depart. ``_blocked`` counts them, so that nobody pays to
        # wake a consumer when none is waiting.
        self._departure = threading.Condition(self._lock)
        self._blocked = 0
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
        self._on_change_callback = _make_change_callback(self)

    @property
    def strict_order(self) -> bool:
        """The ordering policy. Read-only: it selects the indexing strategy."""
        return self._strict_order

    def admit(self, group_id: Hashable, members: Iterable[Hashable]) -> Group:
        """Admit ``members`` as a single group. All of them enter together."""
        # Built outside the lock: validating members can run arbitrary user
        # code (hashing, iterating the ``members`` argument).
        group = Group(group_id, members, 0)
        try:
            hash(group_id)
        except TypeError:
            raise TitoError(f"group id {group_id!r} is not hashable") from None
        with self._lock:
            if group_id in self._groups:
                raise TitoError(
                    f"group {group_id!r} is already in the queue; "
                    f"use a distinct group id"
                )
            member_index = self._member_index
            already_queued = [m for m in group.members if m in member_index]
            if already_queued:
                held_by = {m: member_index[m] for m in already_queued}
                raise TitoError(
                    f"members already in the queue: {already_queued!r} "
                    f"(held by {held_by!r})"
                )
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
            group._on_change = self._on_change_callback
            return group

    def mark_ready(self, member: Hashable) -> bool:
        """Mark a queued ``member`` ready. Returns True if its group is ready."""
        with self._lock:
            return self._holder_of(member).mark_ready(member)

    def mark_waiting(self, member: Hashable) -> None:
        """Mark a queued ``member`` as not ready after all.

        Its group keeps its place in the queue, but cannot depart until
        ``member`` is marked ready again.
        """
        with self._lock:
            self._holder_of(member).mark_waiting(member)

    def mark_group_ready(self, group_id: Hashable) -> bool:
        """Mark every member of ``group_id`` ready."""
        with self._lock:
            group = self._find(group_id)
            if group is None:
                raise TitoError(
                    f"group {group_id!r} is not in the queue; it was never "
                    f"admitted, or it has already departed"
                )
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

    def get(self, group_id: Hashable) -> Optional[Group]:
        """The waiting group admitted as ``group_id``, or None if not queued."""
        with self._lock:
            return self._find(group_id)

    def cancel(self, group_id: Hashable) -> Group:
        """Withdraw a waiting group from the queue and return it.

        The whole group leaves together, ready or not: cancelling is the only
        way a group departs without every member being ready.
        """
        with self._lock:
            group = self._find(group_id)
            if group is None:
                raise TitoError(
                    f"group {group_id!r} is not in the queue; it was never "
                    f"admitted, or it has already departed"
                )
            self._remove(group)
            # Cancelling a strict-order head can free the ready group behind it.
            self._wake_next()
            return group

    def clear(self) -> List[Group]:
        """Withdraw every waiting group, in arrival order, and return them."""
        with self._lock:
            cleared = list(self._groups.values())
            for group in cleared:
                group._on_change = None
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

    def release(
        self, block: bool = False, timeout: Optional[float] = None
    ) -> Optional[Group]:
        """Release the next fully ready group, or None if none can depart.

        By default this returns straight away. With ``block=True`` it sleeps
        until a group can depart, giving up and returning None once
        ``timeout`` seconds have passed, if a timeout is given.
        """
        _check_wait(block, timeout)
        with self._lock:
            if block and not self._wait_for_departure(timeout):
                return None
            group = self._release_next()
            if group is not None:
                self._wake_next()
            return group

    def release_all(
        self, block: bool = False, timeout: Optional[float] = None
    ) -> List[Group]:
        """Release every group that can currently depart, in order.

        With ``block=True`` it first waits, as :meth:`release` does, until at
        least one group can depart; an empty list then means it timed out.
        """
        _check_wait(block, timeout)
        released: List[Group] = []
        with self._lock:
            if block and not self._wait_for_departure(timeout):
                return released
            while True:
                group = self._release_next()
                if group is None:
                    return released
                released.append(group)

    def _holder_of(self, member: Hashable) -> Group:
        """The group holding a queued ``member``; refuses anyone else."""
        group = self.group_of(member)
        if group is None:
            raise TitoError(
                f"{member!r} is not in the queue; admit the group it "
                f"belongs to first, or it may already have departed"
            )
        return group

    def _find(self, group_id: Hashable) -> Optional[Group]:
        """Look up a waiting group; unhashable ids simply match nothing."""
        try:
            return self._groups.get(group_id)
        except TypeError:
            return None

    def _release_next(self) -> Optional[Group]:
        """Remove and return the next group that can depart, if any."""
        group = self.peek()
        if group is not None:
            self._remove(group)
        return group

    def _wait_for_departure(self, timeout: Optional[float]) -> bool:
        """Sleep until a group can depart; False if ``timeout`` ran out first.

        The caller holds the lock, which the condition releases while asleep.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        self._blocked += 1
        try:
            while self.peek() is None:
                if deadline is None:
                    self._departure.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._departure.wait(min(remaining, threading.TIMEOUT_MAX))
            return True
        finally:
            self._blocked -= 1

    def _wake_next(self) -> None:
        """Wake one blocked consumer if a group is able to depart.

        Every change that lets a group depart wakes one consumer, and each
        consumer that releases a group passes the baton on through here, so
        a run of ready groups reaches as many blocked consumers as it can.
        """
        if self._blocked and self.peek() is not None:
            self._departure.notify()

    def _note_change(self, group: Group, ready: bool) -> None:
        """Keep the ready index in step with ``group``, and wake a consumer."""
        if not self._strict_order:
            sequence = group.sequence
            if not ready:
                if self._ready_groups.pop(sequence, None) is not None:
                    self._compact_ready_heap()
            elif sequence not in self._ready_groups:
                self._ready_groups[sequence] = group
                heapq.heappush(self._ready_heap, sequence)
        if ready:
            self._wake_next()

    def _remove(self, group: Group) -> None:
        del self._groups[group.group_id]
        member_index = self._member_index
        for member in group.members:
            del member_index[member]
        group._on_change = None
        if self._ready_groups.pop(group.sequence, None) is not None:
            self._compact_ready_heap()

    def _compact_ready_heap(self) -> None:
        """Drop stale sequences so the ready heap cannot grow without bound.

        ``peek`` only discards stale entries once they reach the top of the
        heap, so groups that departed or stopped being ready would otherwise
        leave their sequence numbers behind forever.
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
        with self._lock:
            waiting = len(self._groups)
            ready = sum(1 for group in self._groups.values() if group.is_ready)
        return (
            f"TitoQueue(strict_order={self._strict_order}, groups={waiting}, "
            f"ready={ready})"
        )
