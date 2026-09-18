import unittest

from tito import Group, TitoError, TitoQueue


class GroupTests(unittest.TestCase):
    def test_group_requires_members(self):
        with self.assertRaises(TitoError):
            Group("g", [], 0)

    def test_group_rejects_duplicate_members(self):
        with self.assertRaises(TitoError):
            Group("g", ["a", "a"], 0)

    def test_ready_tracking(self):
        group = Group("g", ["a", "b"], 0)
        self.assertFalse(group.is_ready)
        self.assertFalse(group.mark_ready("a"))
        self.assertEqual(group.ready_members, ("a",))
        self.assertEqual(group.waiting_members, ("b",))
        self.assertTrue(group.mark_ready("b"))
        self.assertTrue(group.is_ready)

    def test_mark_ready_unknown_member(self):
        group = Group("g", ["a"], 0)
        with self.assertRaises(TitoError):
            group.mark_ready("z")

    def test_mark_ready_is_idempotent(self):
        group = Group("g", ["a", "b"], 0)
        group.mark_ready("a")
        self.assertFalse(group.mark_ready("a"))
        self.assertTrue(group.mark_ready("b"))

    def test_len_iter_contains(self):
        group = Group("g", ["a", "b"], 0)
        self.assertEqual(len(group), 2)
        self.assertEqual(list(group), ["a", "b"])
        self.assertIn("a", group)
        self.assertNotIn("z", group)


class TitoQueueTests(unittest.TestCase):
    def test_group_leaves_only_when_all_ready(self):
        queue = TitoQueue()
        queue.admit("g1", ["a", "b"])
        self.assertIsNone(queue.release())
        queue.mark_ready("a")
        self.assertIsNone(queue.release())
        queue.mark_ready("b")
        released = queue.release()
        self.assertIsNotNone(released)
        self.assertEqual(released.group_id, "g1")
        self.assertEqual(len(queue), 0)
        self.assertNotIn("a", queue)

    def test_strict_order_blocks_younger_ready_groups(self):
        queue = TitoQueue(strict_order=True)
        queue.admit("g1", ["a", "b"])
        queue.admit("g2", ["c"])
        queue.mark_group_ready("g2")
        self.assertIsNone(queue.release())
        queue.mark_group_ready("g1")
        self.assertEqual([g.group_id for g in queue.release_all()], ["g1", "g2"])

    def test_non_strict_order_lets_ready_groups_pass(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a", "b"])
        queue.admit("g2", ["c"])
        queue.mark_group_ready("g2")
        self.assertEqual(queue.release().group_id, "g2")
        self.assertIsNone(queue.release())
        queue.mark_group_ready("g1")
        self.assertEqual(queue.release().group_id, "g1")

    def test_duplicate_group_id_rejected(self):
        queue = TitoQueue()
        queue.admit("g1", ["a"])
        with self.assertRaises(TitoError):
            queue.admit("g1", ["b"])

    def test_member_cannot_be_in_two_groups(self):
        queue = TitoQueue()
        queue.admit("g1", ["a", "b"])
        with self.assertRaises(TitoError):
            queue.admit("g2", ["b", "c"])
        self.assertNotIn("c", queue)
        self.assertEqual(len(queue), 1)

    def test_admit_rejects_empty_group_without_side_effects(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError):
            queue.admit("g1", [])
        self.assertEqual(len(queue), 0)

    def test_mark_ready_unknown_member(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError):
            queue.mark_ready("nobody")

    def test_mark_group_ready_unknown_group(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError):
            queue.mark_group_ready("nope")

    def test_group_of_and_peek(self):
        queue = TitoQueue()
        group = queue.admit("g1", ["a", "b"])
        self.assertIs(queue.group_of("a"), group)
        self.assertIsNone(queue.group_of("z"))
        self.assertIsNone(queue.peek())
        queue.mark_group_ready("g1")
        self.assertIs(queue.peek(), group)
        self.assertEqual(len(queue), 1)

    def test_release_all_empty_queue(self):
        self.assertEqual(TitoQueue().release_all(), [])

    def test_member_can_be_readmitted_after_release(self):
        queue = TitoQueue()
        queue.admit("g1", ["a"])
        queue.mark_group_ready("g1")
        queue.release()
        queue.admit("g2", ["a"])
        self.assertIn("a", queue)

    def test_groups_reported_in_arrival_order(self):
        queue = TitoQueue()
        queue.admit("g1", ["a"])
        queue.admit("g2", ["b"])
        self.assertEqual([g.group_id for g in queue.groups], ["g1", "g2"])


if __name__ == "__main__":
    unittest.main()
