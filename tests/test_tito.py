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

    def test_mark_waiting_takes_back_readiness(self):
        group = Group("g", ["a", "b"], 0)
        group.mark_ready("a")
        group.mark_ready("b")
        group.mark_waiting("a")
        self.assertFalse(group.is_ready)
        self.assertEqual(group.ready_count, 1)
        self.assertEqual(group.waiting_members, ("a",))
        group.mark_waiting("a")
        self.assertEqual(group.ready_count, 1)
        self.assertTrue(group.mark_ready("a"))

    def test_mark_waiting_unknown_member(self):
        group = Group("g", ["a"], 0)
        with self.assertRaises(TitoError):
            group.mark_waiting("z")
        with self.assertRaises(TitoError):
            group.mark_waiting(["unhashable"])

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

    def test_get_finds_waiting_groups_by_id(self):
        queue = TitoQueue()
        group = queue.admit("g1", ["a"])
        self.assertIs(queue.get("g1"), group)
        self.assertIsNone(queue.get("missing"))
        self.assertIsNone(queue.get(["unhashable"]))
        queue.mark_group_ready("g1")
        queue.release()
        self.assertIsNone(queue.get("g1"))

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


class MarkWaitingTests(unittest.TestCase):
    """A member's readiness can be taken back until its group departs."""

    def test_group_cannot_depart_until_member_is_ready_again(self):
        for strict in (True, False):
            with self.subTest(strict_order=strict):
                queue = TitoQueue(strict_order=strict)
                group = queue.admit("g1", ["a", "b"])
                queue.mark_group_ready("g1")
                queue.mark_waiting("a")
                self.assertFalse(group.is_ready)
                self.assertIsNone(queue.peek())
                self.assertIsNone(queue.release())
                self.assertTrue(queue.mark_ready("a"))
                self.assertIs(queue.release(), group)

    def test_strict_head_blocks_again_once_a_member_steps_out(self):
        queue = TitoQueue(strict_order=True)
        queue.admit("g1", ["a"])
        queue.admit("g2", ["b"])
        queue.mark_group_ready("g1")
        queue.mark_group_ready("g2")
        queue.mark_waiting("a")
        self.assertIsNone(queue.release())

    def test_group_ready_again_departs_in_arrival_order(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a"])
        queue.admit("g2", ["b"])
        queue.mark_ready("a")
        queue.mark_waiting("a")
        queue.mark_ready("b")
        queue.mark_ready("a")
        self.assertEqual([g.group_id for g in queue.release_all()], ["g1", "g2"])

    def test_mark_waiting_on_group_object_is_seen_by_queue(self):
        queue = TitoQueue(strict_order=False)
        group = queue.admit("g1", ["a"])
        queue.mark_ready("a")
        group.mark_waiting("a")
        self.assertIsNone(queue.release())
        self.assertEqual(len(queue._ready_groups), 0)

    def test_mark_waiting_refuses_members_not_in_the_queue(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError) as caught:
            queue.mark_waiting("nobody")
        self.assertIn("departed", str(caught.exception))
        with self.assertRaises(TitoError):
            queue.mark_waiting(["unhashable"])


class DiagnosticsTests(unittest.TestCase):
    """Messages and reprs that tell a caller what went wrong, and where."""

    def test_string_members_are_refused_with_a_hint(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError) as caught:
            queue.admit("g", "ann")
        self.assertIn("['ann']", str(caught.exception))
        self.assertNotIn("g", queue._groups)

    def test_duplicate_members_are_named(self):
        with self.assertRaises(TitoError) as caught:
            Group("g", ["a", "b", "a"], 0)
        self.assertIn("duplicate members: ['a']", str(caught.exception))

    def test_unhashable_members_are_named(self):
        with self.assertRaises(TitoError) as caught:
            Group("g", ["a", ["b"]], 0)
        self.assertIn("unhashable members: [['b']]", str(caught.exception))

    def test_double_booking_names_the_holding_group(self):
        queue = TitoQueue()
        queue.admit("g1", ["a"])
        with self.assertRaises(TitoError) as caught:
            queue.admit("g2", ["a"])
        self.assertIn("'a'", str(caught.exception))
        self.assertIn("g1", str(caught.exception))

    def test_unknown_member_and_group_messages_mention_departure(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError) as caught:
            queue.mark_ready("nobody")
        self.assertIn("departed", str(caught.exception))
        with self.assertRaises(TitoError) as caught:
            queue.cancel("missing")
        self.assertIn("departed", str(caught.exception))

    def test_group_repr_shows_who_is_still_waiting(self):
        group = Group("g", ["a", "b"], 0)
        self.assertIn("waiting on ['a', 'b']", repr(group))
        group.mark_ready("a")
        self.assertIn("waiting on ['b']", repr(group))
        group.mark_ready("b")
        self.assertIn("ready=2/2", repr(group))

    def test_queue_repr_counts_waiting_and_ready_groups(self):
        queue = TitoQueue()
        queue.admit("g1", ["a"])
        queue.admit("g2", ["b"])
        queue.mark_ready("a")
        self.assertIn("groups=2", repr(queue))
        self.assertIn("ready=1", repr(queue))


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

    def test_unhashable_admission_raises_tito_error(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError):
            queue.admit("g", [["unhashable"]])
        with self.assertRaises(TitoError):
            queue.admit(["unhashable"], ["a"])
        with self.assertRaises(TitoError):
            Group("g", [["unhashable"]], 0)
        self.assertEqual(len(queue), 0)
        self.assertEqual(queue.groups, ())
        queue.admit("g", ["a"])
        self.assertEqual(len(queue), 1)

    def test_unhashable_group_id_lookups_raise_tito_error(self):
        queue = TitoQueue()
        with self.assertRaises(TitoError):
            queue.cancel(["unhashable"])
        with self.assertRaises(TitoError):
            queue.mark_group_ready(["unhashable"])

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


class BlockingReleaseTests(unittest.TestCase):
    """Consumers can sleep until a group can depart instead of polling."""

    def _start(self, call):
        """Run ``call(block=True)`` on a daemon thread; returns (thread, results).

        There is no timeout, so a consumer that is never woken hangs, and
        ``_finish`` reports it, instead of quietly picking the group up late.
        """
        results = []
        thread = threading.Thread(
            target=lambda: results.append(call(block=True)), daemon=True
        )
        thread.start()
        return thread, results

    def _finish(self, *threads):
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive(), "a blocked consumer was never woken")

    def _until_blocked(self, queue, count=1):
        deadline = time.monotonic() + 5
        while queue._blocked < count:
            self.assertLess(time.monotonic(), deadline, "consumer never blocked")
            time.sleep(0.001)

    def test_blocked_release_wakes_when_group_becomes_ready(self):
        for strict in (True, False):
            with self.subTest(strict_order=strict):
                queue = TitoQueue(strict_order=strict)
                group = queue.admit("g1", ["a", "b"])
                thread, results = self._start(queue.release)
                self._until_blocked(queue)
                queue.mark_ready("a")
                group.mark_ready("b")
                self._finish(thread)
                self.assertEqual(results, [group])

    def test_blocked_release_times_out_with_none(self):
        queue = TitoQueue()
        queue.admit("g1", ["a"])
        start = time.monotonic()
        self.assertIsNone(queue.release(block=True, timeout=0.05))
        self.assertGreaterEqual(time.monotonic() - start, 0.05)
        self.assertEqual(queue.release_all(block=True, timeout=0), [])
        self.assertEqual(len(queue), 1)

    def test_strict_blocked_release_waits_for_the_head(self):
        queue = TitoQueue(strict_order=True)
        queue.admit("g1", ["a"])
        queue.admit("g2", ["b"])
        queue.mark_ready("b")
        self.assertIsNone(queue.release(block=True, timeout=0.05))
        thread, results = self._start(queue.release)
        self._until_blocked(queue)
        queue.cancel("g1")
        self._finish(thread)
        self.assertEqual([g.group_id for g in results], ["g2"])

    def test_blocked_release_all_waits_then_drains_every_departing_group(self):
        queue = TitoQueue(strict_order=True)
        queue.admit("g1", ["a"])
        queue.admit("g2", ["b"])
        queue.mark_ready("b")
        thread, results = self._start(queue.release_all)
        self._until_blocked(queue)
        queue.mark_ready("a")
        self._finish(thread)
        self.assertEqual([[g.group_id for g in r] for r in results], [["g1", "g2"]])

    def test_departing_head_wakes_a_consumer_for_each_ready_group_behind_it(self):
        queue = TitoQueue(strict_order=True)
        queue.admit("head", ["h"])
        for i in range(3):
            queue.admit(f"g{i}", [f"m{i}"])
            queue.mark_ready(f"m{i}")
        consumers = [self._start(queue.release) for _ in range(4)]
        self._until_blocked(queue, 4)
        queue.mark_ready("h")
        self._finish(*(thread for thread, _ in consumers))
        released = [group.group_id for _, results in consumers for group in results]
        self.assertEqual(sorted(released), ["g0", "g1", "g2", "head"])

    def test_blocked_consumers_receive_every_group_exactly_once(self):
        total, consumers = 300, 4
        for strict in (True, False):
            with self.subTest(strict_order=strict):
                queue = TitoQueue(strict_order=strict)
                stops = [("stop", n) for n in range(consumers)]
                seen = []
                lock = threading.Lock()

                def consume():
                    while True:
                        group = queue.release(block=True)
                        if group.group_id in stops:
                            return
                        with lock:
                            seen.append(group.group_id)

                threads = [
                    threading.Thread(target=consume, daemon=True)
                    for _ in range(consumers)
                ]
                for thread in threads:
                    thread.start()
                ids = list(range(total)) + stops
                # Readying each batch back to front leaves a run of ready
                # groups queued behind a head that is still waiting.
                for start in range(0, len(ids), 10):
                    batch = ids[start:start + 10]
                    for group_id in batch:
                        queue.admit(group_id, [group_id])
                    for group_id in reversed(batch):
                        queue.mark_ready(group_id)
                self._finish(*threads)
                self.assertEqual(sorted(seen), list(range(total)))
                self.assertEqual(len(queue), 0)

    def test_invalid_timeouts_are_refused(self):
        queue = TitoQueue()
        for call in (queue.release, queue.release_all):
            with self.assertRaises(TitoError) as caught:
                call(timeout=1)
            self.assertIn("block=True", str(caught.exception))
            for timeout in (-1, float("nan"), "5"):
                with self.assertRaises(TitoError):
                    call(block=True, timeout=timeout)


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

    def test_ready_waiting_churn_does_not_grow_ready_heap(self):
        queue = TitoQueue(strict_order=False)
        queue.admit("g1", ["a", "b"])
        queue.mark_ready("a")
        for _ in range(5000):
            queue.mark_ready("b")
            queue.mark_waiting("b")
        self.assertLess(len(queue._ready_heap), 100)
        self.assertEqual(len(queue._ready_groups), 0)

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
