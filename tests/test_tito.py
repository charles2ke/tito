import gc
import threading
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


class HardeningTests(unittest.TestCase):
    """Invariants that keep a long-running queue consistent."""

    def test_strict_order_is_read_only(self):
        queue = TitoQueue(strict_order=True)
        with self.assertRaises(AttributeError):
            queue.strict_order = False
        self.assertTrue(queue.strict_order)

    def test_group_sequence_is_read_only(self):
        group = Group("g", ["a"], 7)
        self.assertEqual(group.sequence, 7)
        with self.assertRaises(AttributeError):
            group.sequence = 0

    def test_unhashable_member_lookups_do_not_raise_type_error(self):
        queue = TitoQueue()
        group = queue.admit("g", ["a"])
        self.assertNotIn(["unhashable"], queue)
        self.assertNotIn(["unhashable"], group)
        self.assertIsNone(queue.group_of(["unhashable"]))
        with self.assertRaises(TitoError):
            queue.mark_ready(["unhashable"])
        with self.assertRaises(TitoError):
            group.mark_ready(["unhashable"])

    def test_ready_count_tracks_marked_members(self):
        group = Group("g", ["a", "b"], 0)
        self.assertEqual(group.ready_count, 0)
        group.mark_ready("a")
        group.mark_ready("a")
        self.assertEqual(group.ready_count, 1)
        group.mark_ready("b")
        self.assertEqual(group.ready_count, 2)
        self.assertIn("ready=2/2", repr(group))

    def test_repeat_mark_ready_reports_group_state(self):
        group = Group("g", ["a", "b"], 0)
        group.mark_ready("a")
        self.assertFalse(group.mark_ready("a"))
        group.mark_ready("b")
        self.assertTrue(group.mark_ready("a"))

    def test_strict_queue_keeps_no_ready_index(self):
        queue = TitoQueue(strict_order=True)
        queue.admit("g1", ["a"])
        queue.mark_group_ready("g1")
        self.assertEqual(len(queue._ready_groups), 0)
        self.assertEqual(len(queue._ready_heap), 0)
        self.assertEqual(queue.release().group_id, "g1")

    def test_queue_has_no_instance_dict(self):
        self.assertFalse(hasattr(TitoQueue(), "__dict__"))
        self.assertFalse(hasattr(Group("g", ["a"], 0), "__dict__"))


class ThreadSafetyTests(unittest.TestCase):
    """Concurrent callers must never corrupt or double-release a group."""

    def _run(self, workers):
        errors = []
        barrier = threading.Barrier(len(workers))

        def target(fn):
            try:
                barrier.wait()
                fn()
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=target, args=(fn,)) for fn in workers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])

    def test_shares_lock_with_admitted_groups(self):
        queue = TitoQueue()
        group = queue.admit("g1", ["a"])
        self.assertIs(group._lock, queue._lock)

    def test_standalone_group_has_its_own_lock(self):
        self.assertIsNot(Group("g", ["a"], 0)._lock, Group("g", ["a"], 0)._lock)

    def test_concurrent_mark_ready_counts_each_member_once(self):
        size = 500
        queue = TitoQueue()
        group = queue.admit("big", range(size))
        halves = [range(0, size), range(size - 1, -1, -1)]
        self._run([
            (lambda members=members: [queue.mark_ready(m) for m in members])
            for members in halves
        ])
        self.assertEqual(group.ready_count, size)
        self.assertIs(queue.release(), group)
        self.assertEqual(len(queue), 0)

    def test_concurrent_release_never_hands_out_a_group_twice(self):
        count = 300
        for strict in (True, False):
            with self.subTest(strict_order=strict):
                queue = TitoQueue(strict_order=strict)
                for i in range(count):
                    queue.admit(i, [f"m{i}-{strict}"])
                    queue.mark_group_ready(i)
                seen = []
                lock = threading.Lock()

                def drain():
                    while True:
                        group = queue.release()
                        if group is None:
                            return
                        with lock:
                            seen.append(group.group_id)

                self._run([drain] * 4)
                self.assertEqual(sorted(seen), list(range(count)))
                self.assertEqual(len(queue), 0)

    def test_concurrent_admit_assigns_unique_sequences(self):
        queue = TitoQueue(strict_order=False)
        per_thread = 200
        threads = 4

        def admit(offset):
            for i in range(per_thread):
                queue.admit((offset, i), [f"m{offset}-{i}"])

        self._run([lambda o=o: admit(o) for o in range(threads)])
        sequences = [g.sequence for g in queue.groups]
        self.assertEqual(len(set(sequences)), per_thread * threads)
        self.assertEqual(sequences, sorted(sequences))

    def test_concurrent_admit_rejects_duplicate_group_ids(self):
        queue = TitoQueue()
        wins = []
        lock = threading.Lock()

        def admit():
            try:
                queue.admit("same", [threading.get_ident()])
            except TitoError:
                return
            with lock:
                wins.append(1)

        self._run([admit] * 8)
        self.assertEqual(len(wins), 1)
        self.assertEqual(len(queue), 1)

    def test_producers_and_consumers_release_every_group(self):
        queue = TitoQueue(strict_order=False)
        total = 400
        produced = threading.Event()
        seen = []
        lock = threading.Lock()

        def produce():
            for i in range(total):
                queue.admit(i, [f"p{i}"])
                queue.mark_group_ready(i)
            produced.set()

        def consume():
            while True:
                for group in queue.release_all():
                    with lock:
                        seen.append(group.group_id)
                if produced.is_set() and len(queue) == 0:
                    return

        self._run([produce, consume, consume])
        self.assertEqual(sorted(seen), list(range(total)))

    def test_cancel_and_release_do_not_both_claim_a_group(self):
        queue = TitoQueue(strict_order=False)
        count = 200
        for i in range(count):
            queue.admit(i, [f"c{i}"])
            queue.mark_group_ready(i)
        claimed = []
        lock = threading.Lock()

        def cancel_all():
            for i in range(count):
                try:
                    group = queue.cancel(i)
                except TitoError:
                    continue
                with lock:
                    claimed.append(group.group_id)

        def release_all():
            while len(queue):
                for group in queue.release_all():
                    with lock:
                        claimed.append(group.group_id)

        self._run([cancel_all, release_all])
        self.assertEqual(sorted(claimed), list(range(count)))
        self.assertEqual(len(queue), 0)
        self.assertEqual(len(queue._member_index), 0)
        self.assertEqual(len(queue._ready_groups), 0)


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
        self.assertEqual(len(queue._ready_groups), 0)

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
        self.assertEqual(len(queue._ready_groups), 0)

    def test_clear_returns_groups_in_arrival_order(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a"])
        group2 = queue.admit("g2", ["b"])
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
        self.assertEqual(len(queue._ready_groups), 0)
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
