"""Together In Together Out - Python example.

Run: python examples/tito_example.py
"""

from collections import OrderedDict


class TitoError(Exception):
    """Raised when an operation would violate the TITO invariants."""


class Group:
    """A set of members that entered the queue together.

    A group is only ever released as a whole: it departs when, and only
    when, all of its members have been marked ready.
    """

    def __init__(self, group_id, members):
        members = list(members)
        if not members:
            raise TitoError("group %s must contain at least one member" % group_id)
        ready = OrderedDict((member, False) for member in members)
        if len(ready) != len(members):
            raise TitoError("group %s contains duplicate members" % group_id)
        self.group_id = group_id
        self.members = members
        self._ready = ready
        self._ready_count = 0

    @property
    def ready_members(self):
        """Members already marked ready, in admission order."""
        return [member for member in self.members if self._ready[member]]

    @property
    def waiting_members(self):
        """Members not yet marked ready, in admission order."""
        return [member for member in self.members if not self._ready[member]]

    @property
    def ready_count(self):
        """How many members have been marked ready."""
        return self._ready_count

    @property
    def is_ready(self):
        """True once every member of the group is ready to depart."""
        return self._ready_count == len(self.members)

    def mark_ready(self, member):
        """Mark one member ready. Returns True if the whole group is ready."""
        if member not in self._ready:
            raise TitoError("%s is not a member of group %s" % (member, self.group_id))
        if not self._ready[member]:
            self._ready[member] = True
            self._ready_count += 1
        return self.is_ready

    def __len__(self):
        return len(self.members)

    def __contains__(self, member):
        return member in self._ready

    def __repr__(self):
        return "%s [%s]" % (self.group_id, " ".join(self.members))


class TitoQueue:
    """A queue that admits and releases members group by group.

    ``strict_order=True`` (the default) is head-of-line FIFO: only the oldest
    waiting group may depart. ``strict_order=False`` lets any fully ready
    group depart, still oldest first, so a waiting group does not block the
    ready groups behind it.
    """

    def __init__(self, strict_order=True):
        self.strict_order = strict_order
        self._groups = OrderedDict()
        self._member_index = {}

    def admit(self, group_id, members):
        """Admit members as one group. Returns the admitted group."""
        group = Group(group_id, members)
        if group_id in self._groups:
            raise TitoError("group %s is already in the queue" % group_id)
        queued = [member for member in group.members if member in self._member_index]
        if queued:
            raise TitoError("members already in the queue: %s" % " ".join(queued))
        self._groups[group_id] = group
        for member in group.members:
            self._member_index[member] = group_id
        return group

    def mark_ready(self, member):
        """Mark a queued member ready. Returns True if its group is ready."""
        group = self.group_of(member)
        if group is None:
            raise TitoError("%s is not in the queue" % member)
        return group.mark_ready(member)

    def mark_group_ready(self, group_id):
        """Mark every member of a queued group ready."""
        group = self._groups.get(group_id)
        if group is None:
            raise TitoError("group %s is not in the queue" % group_id)
        for member in group.members:
            group.mark_ready(member)
        return True

    def group_of(self, member):
        """The group a queued member belongs to, or None if not queued."""
        group_id = self._member_index.get(member)
        if group_id is None:
            return None
        return self._groups[group_id]

    def peek(self):
        """The next group that would be released, without releasing it."""
        for group in self._groups.values():
            if group.is_ready:
                return group
            if self.strict_order:
                # Head of the line blocks every group behind it.
                return None
        return None

    def release(self):
        """Release the next fully ready group, or None if none can depart."""
        group = self.peek()
        if group is None:
            return None
        self._remove(group)
        return group

    def release_all(self):
        """Release every group that can currently depart, in order."""
        released = []
        while True:
            group = self.release()
            if group is None:
                return released
            released.append(group)

    def cancel(self, group_id):
        """Withdraw a waiting group, ready or not, and return it."""
        group = self._groups.get(group_id)
        if group is None:
            raise TitoError("group %s is not in the queue" % group_id)
        self._remove(group)
        return group

    def clear(self):
        """Withdraw every waiting group, in arrival order, and return them."""
        cleared = list(self._groups.values())
        self._groups.clear()
        self._member_index.clear()
        return cleared

    @property
    def groups(self):
        """Waiting groups, in arrival order."""
        return list(self._groups.values())

    def _remove(self, group):
        del self._groups[group.group_id]
        for member in group.members:
            del self._member_index[member]

    def __len__(self):
        return len(self._groups)

    def __contains__(self, member):
        return member in self._member_index

    def __repr__(self):
        return "TitoQueue(strict_order=%s, groups=%d)" % (self.strict_order, len(self._groups))


def flag(value):
    """Format a boolean the same way in every example language."""
    return "true" if value else "false"


def show(group):
    """Format an optional group, as returned by peek() and release()."""
    return "waiting" if group is None else "%s" % group


def show_all(groups):
    """Format the group lists returned by release_all() and clear()."""
    if not groups:
        return "none"
    return ", ".join("%s" % group for group in groups)


def show_ids(groups):
    """Format the group ids of the waiting groups."""
    if not groups:
        return "none"
    return " ".join("%s" % group.group_id for group in groups)


def strict_order_demo():
    """Head-of-line FIFO: party-2 waits behind party-1 until it departs."""
    print("-- strict order --")
    queue = TitoQueue()
    print("admit %s" % queue.admit("party-1", ["ann", "bob"]))
    print("admit %s" % queue.admit("party-2", ["cy"]))
    print("len %d, groups %s" % (len(queue), show_ids(queue.groups)))
    print("contains ann %s, contains zoe %s" % (flag("ann" in queue), flag("zoe" in queue)))

    party1 = queue.group_of("bob")
    print("group_of bob -> %s" % party1.group_id)
    print("party-1: size %d, contains ann %s, contains zoe %s"
          % (len(party1), flag("ann" in party1), flag("zoe" in party1)))

    print("mark_ready ann -> group ready %s" % flag(queue.mark_ready("ann")))
    print("party-1: %d/%d ready [%s] waiting [%s] is_ready %s"
          % (party1.ready_count, len(party1), " ".join(party1.ready_members),
             " ".join(party1.waiting_members), flag(party1.is_ready)))
    print("peek -> %s" % show(queue.peek()))
    print("release -> %s" % show(queue.release()))

    print("party-1.mark_ready bob -> group ready %s" % flag(party1.mark_ready("bob")))
    print("party-1: %d/%d ready [%s] waiting [%s] is_ready %s"
          % (party1.ready_count, len(party1), " ".join(party1.ready_members),
             " ".join(party1.waiting_members), flag(party1.is_ready)))
    print("peek -> %s" % show(queue.peek()))
    print("release -> %s" % show(queue.release()))

    print("mark_group_ready party-2 -> %s" % flag(queue.mark_group_ready("party-2")))
    print("release_all -> %s" % show_all(queue.release_all()))
    print("len %d" % len(queue))


def relaxed_order_demo():
    """Without strict order, ready party-4 leaves ahead of waiting party-3."""
    print("-- relaxed order --")
    queue = TitoQueue(strict_order=False)
    print("strict_order %s" % flag(queue.strict_order))
    print("admit %s" % queue.admit("party-3", ["dee", "eli"]))
    print("admit %s" % queue.admit("party-4", ["fay"]))

    print("mark_group_ready party-4 -> %s" % flag(queue.mark_group_ready("party-4")))
    print("peek -> %s" % show(queue.peek()))
    print("release -> %s" % show(queue.release()))

    print("mark_ready dee -> group ready %s" % flag(queue.mark_ready("dee")))
    print("release -> %s" % show(queue.release()))
    print("mark_ready eli -> group ready %s" % flag(queue.mark_ready("eli")))
    print("release_all -> %s" % show_all(queue.release_all()))
    print("len %d" % len(queue))


def cancel_and_clear_demo():
    """Cancelling is the only way a group leaves before it is fully ready."""
    print("-- cancel and clear --")
    queue = TitoQueue()
    print("admit %s" % queue.admit("party-5", ["gil", "hal"]))
    print("admit %s" % queue.admit("party-6", ["ivy"]))
    print("admit %s" % queue.admit("party-7", ["jay"]))

    print("mark_ready gil -> group ready %s" % flag(queue.mark_ready("gil")))
    cancelled = queue.cancel("party-5")
    print("cancel party-5 -> %s %d/%d ready" % (cancelled, cancelled.ready_count, len(cancelled)))
    print("groups %s" % show_ids(queue.groups))
    print("clear -> %s" % show_all(queue.clear()))
    print("len %d, contains ivy %s" % (len(queue), flag("ivy" in queue)))


def attempt(label, action):
    """Run an operation that must fail, and print the reported reason."""
    try:
        action()
    except TitoError as error:
        print("%s -> %s" % (label, error))
    else:
        print("%s -> no error" % label)


def error_demo():
    """Every operation that would break the TITO invariants is rejected."""
    print("-- errors --")
    queue = TitoQueue()
    print("admit %s" % queue.admit("party-8", ["kim"]))

    attempt("admit party-8 [kim]", lambda: queue.admit("party-8", ["kim"]))
    attempt("admit party-9 []", lambda: queue.admit("party-9", []))
    attempt("admit party-9 [jay jay]", lambda: queue.admit("party-9", ["jay", "jay"]))
    attempt("admit party-9 [kim]", lambda: queue.admit("party-9", ["kim"]))
    attempt("mark_ready zoe", lambda: queue.mark_ready("zoe"))
    attempt("party-8.mark_ready zoe", lambda: queue.group_of("kim").mark_ready("zoe"))
    attempt("mark_group_ready party-9", lambda: queue.mark_group_ready("party-9"))
    attempt("cancel party-9", lambda: queue.cancel("party-9"))


def main():
    strict_order_demo()
    print("")
    relaxed_order_demo()
    print("")
    cancel_and_clear_demo()
    print("")
    error_demo()


if __name__ == "__main__":
    main()
