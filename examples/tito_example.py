"""Together In Together Out - Python example.

Run: python examples/tito_example.py
"""

from collections import OrderedDict, deque


class TitoQueue:
    """Minimal strict-order (head-of-line FIFO) TITO queue."""

    def __init__(self):
        self._order = deque()
        self._groups = {}
        self._group_of = {}

    def admit(self, group_id, members):
        members = list(members)
        if not members:
            raise ValueError("a group must contain at least one member")
        if group_id in self._groups:
            raise ValueError("duplicate group id: %r" % (group_id,))
        ready = OrderedDict()
        for member in members:
            if member in self._group_of or member in ready:
                raise ValueError("duplicate member: %r" % (member,))
            ready[member] = False
        for member in members:
            self._group_of[member] = group_id
        self._groups[group_id] = ready
        self._order.append(group_id)

    def mark_ready(self, member):
        group_id = self._group_of.get(member)
        if group_id is None:
            raise ValueError("unknown member: %r" % (member,))
        self._groups[group_id][member] = True

    def release(self):
        """Release the head group, or None while it is not fully ready."""
        if not self._order:
            return None
        group_id = self._order[0]
        ready = self._groups[group_id]
        if not all(ready.values()):
            return None
        self._order.popleft()
        del self._groups[group_id]
        for member in ready:
            del self._group_of[member]
        return group_id, list(ready)


def main():
    queue = TitoQueue()

    queue.admit("party-1", ["ann", "bob"])
    print("admit party-1: ann, bob")
    queue.admit("party-2", ["cy"])
    print("admit party-2: cy")

    for member in ("ann", "bob", "cy"):
        queue.mark_ready(member)
        print("ready %s" % member)
        released = queue.release()
        if released is None:
            print("release -> waiting")
        else:
            group_id, members = released
            print("release -> %s [%s]" % (group_id, " ".join(members)))


if __name__ == "__main__":
    main()
