import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"))

import practical_usage  # noqa: E402


def run(scenario):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        scenario()
    return buffer.getvalue()


class PracticalUsageTests(unittest.TestCase):
    def test_restaurant_seats_parties_whole_and_in_arrival_order(self):
        output = run(practical_usage.restaurant_seating)
        self.assertIn("ready to seat: None", output)
        self.assertLess(output.index("seat mehta-party"), output.index("seat okafor-party"))
        self.assertIn("seat mehta-party: asha raj priya", output)

    def test_matchmaking_starts_the_complete_lobby_first(self):
        output = run(practical_usage.matchmaking_lobby)
        self.assertLess(output.index("lobby-beta"), output.index("start match: lobby-alpha"))
        self.assertIn("lobbies waiting: 0", output)

    def test_batch_publish_is_all_or_nothing(self):
        output = run(practical_usage.batch_publish)
        self.assertIn("publish 2026-09-18: 3 shards", output)
        self.assertNotIn("publish 2026-09-19", output)
        self.assertIn("rolled back 2026-09-19, 2/3 shards computed", output)

    def test_fan_out_answers_once_every_part_is_ready(self):
        output = run(practical_usage.parallel_fan_out)
        self.assertIn(
            "respond to request-7 with 3 parts: orders-data profile-data recommendations-data",
            output,
        )

    def test_guarded_admission_refuses_double_booking(self):
        output = run(practical_usage.guarded_admission)
        self.assertIn("refused: members already in the queue", output)
        self.assertIn("shift-a intact: ['nurse-1', 'nurse-2']", output)

    def test_main_runs_every_scenario(self):
        output = run(practical_usage.main)
        for heading in (
            "-- restaurant seating (strict order) --",
            "-- matchmaking lobbies (relaxed order) --",
            "-- batch publishing (all-or-nothing) --",
            "-- parallel fan-out (thread-safe) --",
            "-- guarded admission --",
        ):
            self.assertIn(heading, output)


if __name__ == "__main__":
    unittest.main()
