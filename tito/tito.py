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

from collections import OrderedDict
from typing import Dict, Hashable, Iterable, List, Optional, Tuple

__all__ = ["Group", "TitoError", "TitoQueue"]


class TitoError(Exception):
    """Raised when an operation would violate the TITO invariants."""


class Group:
    """A set of members that entered the queue together.

    A group is only ever released as a whole: it departs when, and only
    when, all of its members have been marked ready.
    """

    __slots__ = ("group_id", "_members", "_ready", "sequence")

    def __init__(self, group_id: Hashable, members: Iterable[Hashable], sequence: int) -> None:
        member_list: Tuple[Hashable, ...] = tuple(members)
        if not member_list:
            raise TitoError(f"group {group_id!r} must contain at least one member")
        if len(set(member_list)) != len(member_list):
            raise TitoError(f"group {group_id!r} contains duplicate members")
        self.group_id = group_id
        self._members = member_list
        self._ready: set = set()
        self.sequence = sequence

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
        if member not in set(self._members):
            raise TitoError(f"{member!r} is not a member of group {self.group_id!r}")
        self._ready.add(member)
        return self.is_ready

    def __len__(self) -> int:
        return len(self._members)

    def __iter__(self):
        return iter(self._members)

    def __contains__(self, member: Hashable) -> bool:
        return member in self._members

    def __repr__(self) -> str:
        return (
            f"Group(group_id={self.group_id!r}, members={list(self._members)!r}, "
            f"ready={len(self._ready)}/{len(self._members)})"
        )


class TitoQueue:
    """A queue that admits and releases members group-by-group."""

    def __init__(self, strict_order: bool = True) -> None:
        self.strict_order = strict_order
        self._groups: "OrderedDict[Hashable, Group]" = OrderedDict()
        self._member_index: Dict[Hashable, Hashable] = {}
        self._sequence = 0

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

    def peek(self) -> Optional[Group]:
        """The next group that would be released, without releasing it."""
        for group in self._groups.values():
            if group.is_ready:
                return group
            if self.strict_order:
                return None
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

    def _remove(self, group: Group) -> None:
        del self._groups[group.group_id]
        for member in group.members:
            del self._member_index[member]

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
