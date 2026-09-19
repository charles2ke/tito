"""Practical uses of the TITO discipline, with the real ``tito`` package.

Unlike the thirteen ``tito_example.*`` files, which reimplement the API from
scratch and all print the same tour of it, this file shows *why* you would
reach for a TITO queue: four small, realistic problems where work must be
admitted and released group by group.

Run: python examples/practical_usage.py
"""

import os
import sys
import threading

# Allows running the file straight from a checkout, without installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tito import TitoError, TitoQueue  # noqa: E402


def restaurant_seating():
    """Seat walk-in parties fairly: whole party, in the order they arrived.

    A restaurant with one large table seats a party only once everyone in it
    has turned up, and a party that arrived first is never overtaken. That is
    exactly strict-order TITO: the head of the line blocks the queue, so no
    group is skipped just because a later group happens to be complete.
    """
    print("-- restaurant seating (strict order) --")
    waitlist = TitoQueue()  # strict_order=True: first come, first seated.
    waitlist.admit("mehta-party", ["asha", "raj", "priya"])
    waitlist.admit("okafor-party", ["ngozi", "chidi"])

    for guest in ("asha", "raj", "ngozi", "chidi"):
        waitlist.mark_ready(guest)  # guest has checked in at the host stand
    # The Okafors are all here, but the Mehtas arrived first and are still
    # one guest short, so nobody is seated yet.
    print("ready to seat:", waitlist.peek())
    print("still waiting on:", list(waitlist.group_of("asha").waiting_members))

    waitlist.mark_ready("priya")
    for party in waitlist.release_all():
        print("seat %s: %s" % (party.group_id, " ".join(party.members)))
    print("parties left on the waitlist:", len(waitlist))


def matchmaking_lobby():
    """Start a match as soon as one lobby fills, without freezing the others.

    Players queue as a premade squad and must enter the match together. A
    half-full lobby should not hold up a lobby that is ready to play, so the
    relaxed policy fits: any complete lobby departs, oldest complete one first.
    """
    print("\n-- matchmaking lobbies (relaxed order) --")
    lobbies = TitoQueue(strict_order=False)
    lobbies.admit("lobby-alpha", ["ada", "linus", "grace"])
    lobbies.admit("lobby-beta", ["hedy", "alan"])

    lobbies.mark_ready("ada")  # only one Alpha player has loaded in
    for player in ("hedy", "alan"):
        lobbies.mark_ready(player)

    match = lobbies.release()  # Beta is complete and goes first
    print("start match:", match.group_id, list(match.members))
    print("alpha still loading:", list(lobbies.group_of("ada").waiting_members))

    for player in ("linus", "grace"):
        lobbies.mark_ready(player)
    match = lobbies.release()
    print("start match:", match.group_id, list(match.members))
    print("lobbies waiting:", len(lobbies))


def batch_publish():
    """Publish a dataset only when every shard of it has been computed.

    Downstream consumers must never see half a dataset, so the shards of a
    batch are admitted together and published together. If one shard fails,
    ``cancel`` withdraws the whole batch - the only way a group leaves before
    it is ready - and nothing partial is ever published.
    """
    print("\n-- batch publishing (all-or-nothing) --")
    pending = TitoQueue()
    for day in ("2026-09-18", "2026-09-19"):
        # Members are unique across the whole queue, so scope shard names by
        # the batch they belong to.
        pending.admit(day, [(day, shard) for shard in ("clicks", "views", "spend")])

    for shard in ("clicks", "views", "spend"):
        pending.mark_ready(("2026-09-18", shard))
    for shard in ("clicks", "views"):
        pending.mark_ready(("2026-09-19", shard))

    for batch in pending.release_all():
        print("publish %s: %d shards" % (batch.group_id, len(batch)))

    failed = pending.cancel("2026-09-19")  # the spend job crashed
    print("rolled back %s, %d/%d shards computed"
          % (failed.group_id, failed.ready_count, len(failed)))
    print("nothing half-published:", len(pending) == 0)


def parallel_fan_out():
    """Fan a request out to several services and answer when all replies land.

    Each worker marks its own part ready from its own thread; the queue is
    thread-safe, so no extra locking is needed, and the request is only
    answered once every part of it has completed.
    """
    print("\n-- parallel fan-out (thread-safe) --")
    inflight = TitoQueue()
    parts = ["profile", "orders", "recommendations"]
    inflight.admit("request-7", parts)

    results = {}

    def fetch(part):
        results[part] = "%s-data" % part  # stands in for an I/O call
        inflight.mark_ready(part)

    workers = [threading.Thread(target=fetch, args=(part,)) for part in parts]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    response = inflight.release()
    print("respond to %s with %d parts: %s"
          % (response.group_id, len(response),
             " ".join(sorted(results[part] for part in response.members))))


def guarded_admission():
    """Reject work that would break the invariants, instead of corrupting it."""
    print("\n-- guarded admission --")
    queue = TitoQueue()
    queue.admit("shift-a", ["nurse-1", "nurse-2"])
    try:
        queue.admit("shift-b", ["nurse-2", "nurse-3"])  # double-booked member
    except TitoError as error:
        print("refused:", error)
    print("shift-a intact:", list(queue.group_of("nurse-2").members))


def main():
    restaurant_seating()
    matchmaking_lobby()
    batch_publish()
    parallel_fan_out()
    guarded_admission()


if __name__ == "__main__":
    main()
