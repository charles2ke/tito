import gc
import time
import unittest
import weakref

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

    def test_none_group_id_can_be_marked_ready(self):
        queue = TitoQueue()
        group = queue.admit(None, ["a"])
        self.assertTrue(queue.mark_ready("a"))
        self.assertIs(queue.release(), group)

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


class ReadyTrackingTests(unittest.TestCase):
    """The queue keeps its own index of ready groups; it must stay in sync."""

    def test_marking_ready_on_group_object_is_seen_by_queue(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a", "b"])
        group = queue.admit("g2", ["c"])
        group.mark_ready("c")
        self.assertIs(queue.release(), group)

    def test_non_strict_releases_in_arrival_order_not_ready_order(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a"])
        queue.admit("g2", ["b"])
        queue.admit("g3", ["c"])
        queue.mark_group_ready("g3")
        queue.mark_group_ready("g1")
        queue.mark_group_ready("g2")
        self.assertEqual([g.group_id for g in queue.release_all()], ["g1", "g2", "g3"])

    def test_redundant_mark_ready_does_not_duplicate_release(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a", "b"])
        queue.mark_group_ready("g1")
        queue.mark_group_ready("g1")
        self.assertEqual([g.group_id for g in queue.release_all()], ["g1"])

    def test_released_group_does_not_reenter_queue(self):
        queue = TitoQueue(strict_order=False)
        group = queue.admit("g1", ["a", "b"])
        queue.mark_group_ready("g1")
        self.assertIs(queue.release(), group)
        group.mark_ready("a")
        self.assertIsNone(queue.release())
        self.assertEqual(len(queue), 0)

    def test_readmitted_group_is_tracked_independently(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a"])
        queue.mark_group_ready("g1")
        queue.release()
        queue.admit("g1", ["a"])
        self.assertIsNone(queue.release())
        queue.mark_group_ready("g1")
        self.assertEqual(queue.release().group_id, "g1")

    def test_interleaved_admit_ready_release_non_strict(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("blocked", ["x", "y"])
        released = []
        for i in range(5):
            queue.admit(i, [f"m{i}"])
            queue.mark_group_ready(i)
            group = queue.release()
            released.append(group.group_id)
        self.assertEqual(released, [0, 1, 2, 3, 4])
        self.assertEqual(len(queue), 1)
        self.assertIsNone(queue.release())


class CancellationTests(unittest.TestCase):
    """Cancelling withdraws a whole group without releasing it."""

    def test_cancel_removes_group_and_members(self):
        queue = TitoQueue()
        group = queue.admit("g1", ["a", "b"])
        self.assertIs(queue.cancel("g1"), group)
        self.assertEqual(len(queue), 0)
        self.assertNotIn("a", queue)
        self.assertIsNone(queue.group_of("b"))

    def test_cancel_unknown_group(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError):
            queue.cancel("nope")

    def test_cancel_unblocks_strict_head(self):
        queue = TitoQueue(strict_order=True)
        queue.admit("g1", ["a", "b"])
        queue.admit("g2", ["c"])
        queue.mark_group_ready("g2")
        self.assertIsNone(queue.release())
        queue.cancel("g1")
        self.assertEqual(queue.release().group_id, "g2")

    def test_cancelled_ready_group_does_not_reappear(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a"])
        queue.mark_group_ready("g1")
        queue.cancel("g1")
        self.assertIsNone(queue.release())
        self.assertEqual(len(queue._ready_seqs), 0)

    def test_cancelled_group_can_be_readmitted(self):
        queue = TitoQueue()
        queue.admit("g1", ["a"])
        queue.cancel("g1")
        queue.admit("g1", ["a"])
        self.assertIn("a", queue)
        self.assertIsNone(queue.release())

    def test_cancelled_group_does_not_notify_queue(self):
        queue = TitoQueue(strict_order=False)
        group = queue.admit("g1", ["a", "b"])
        queue.cancel("g1")
        group.mark_ready("a")
        group.mark_ready("b")
        self.assertIsNone(queue.release())
        self.assertEqual(len(queue._ready_seqs), 0)

    def test_clear_returns_groups_in_arrival_order(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a"])
        group2 = queue.admit("g2", ["b"])
        queue.mark_group_ready("g2")
        self.assertEqual([g.group_id for g in queue.clear()], ["g1", "g2"])
        self.assertEqual(len(queue), 0)
        self.assertNotIn("a", queue)
        self.assertIsNone(queue.release())
        group2.mark_ready("b")
        self.assertIsNone(queue.release())

    def test_clear_empty_queue(self):
        self.assertEqual(TitoQueue().clear(), [])


class ScalingTests(unittest.TestCase):
    """Guards against the quadratic behaviour these paths used to have."""

    def test_non_strict_peek_does_not_rescan_blocked_groups(self):
        queue = TitoQueue(strict_order=False)
        for i in range(200):
            queue.admit(f"blocked{i}", [f"x{i}", f"y{i}"])
        queue.admit("ready", ["r"])
        queue.mark_group_ready("ready")

        original = Group.is_ready
        calls = []
        Group.is_ready = property(lambda self: calls.append(1) or original.fget(self))
        try:
            group = queue.release()
        finally:
            Group.is_ready = original

        self.assertEqual(group.group_id, "ready")
        self.assertLessEqual(len(calls), 2, "peek scanned the blocked prefix")

    def test_mark_ready_is_constant_time_per_member(self):
        size = 20000
        queue = TitoQueue()
        queue.admit("big", range(size))
        start = time.perf_counter()
        for member in range(size):
            queue.mark_ready(member)
        elapsed = time.perf_counter() - start
        self.assertIsNotNone(queue.release())
        self.assertLess(elapsed, 2.0, "mark_ready appears to scale super-linearly")


class MemoryTests(unittest.TestCase):
    """Long-lived queues must not accumulate state for departed groups."""

    def _churn(self, queue, count):
        for i in range(count):
            queue.admit(i, [f"m{i}"])
            queue.mark_group_ready(i)
            queue.release()

    def test_strict_order_churn_does_not_grow_ready_heap(self):
        queue = TitoQueue(strict_order=True)
        self._churn(queue, 5000)
        self.assertEqual(len(queue), 0)
        self.assertLess(len(queue._ready_heap), 100)
        self.assertEqual(len(queue._ready_seqs), 0)
        self.assertEqual(len(queue._ready_groups), 0)
        self.assertEqual(len(queue._member_index), 0)

    def test_non_strict_churn_does_not_grow_ready_heap(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("blocked", ["x", "y"])
        self._churn(queue, 5000)
        self.assertEqual(len(queue), 1)
        self.assertLess(len(queue._ready_heap), 100)

    def test_queue_is_not_kept_alive_by_its_groups(self):
        gc.disable()
        try:
            queue = TitoQueue()
            queue.admit("g1", ["a", "b"])
            ref = weakref.ref(queue)
            del queue
            self.assertIsNone(ref(), "queue leaked through a reference cycle")
        finally:
            gc.enable()

    def test_released_group_still_reports_ready(self):
        queue = TitoQueue()
        group = queue.admit("g1", ["a", "b"])
        queue.mark_ready("a")
        self.assertIs(queue.release(), None)
        queue.mark_ready("b")
        self.assertIs(queue.release(), group)
        self.assertTrue(group.is_ready)


if __name__ == "__main__":
    unittest.main()
