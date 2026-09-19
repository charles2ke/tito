# tito

Together In Together Out

TITO is a batch scheduling discipline: members that enter the system as a group
are never split up while they wait, and they only leave once *every* member of
their group is ready to go.

## Usage

```python
from tito import TitoQueue

queue = TitoQueue()               # strict_order=True by default
queue.admit("party-1", ["ann", "bob"])
queue.admit("party-2", ["cy"])

queue.mark_ready("ann")
queue.release()                   # None - "bob" is not ready yet

queue.mark_ready("bob")
queue.release()                   # Group(group_id='party-1', ...)
```

The same discipline written from scratch in thirteen popular languages lives in
[`examples/`](examples/README.md) - C, C++, C#, Go, Java, JavaScript, Kotlin,
PHP, Python, Ruby, Rust, Swift and TypeScript.

### Ordering policies

- `TitoQueue(strict_order=True)` (default): head-of-line FIFO. Only the oldest
  waiting group may depart, so groups always exit in arrival order.
- `TitoQueue(strict_order=False)`: any fully ready group may depart, so a group
  that is still waiting does not block younger ready groups.

### API

- `admit(group_id, members)` - admit a group; members enter together.
- `mark_ready(member)` / `mark_group_ready(group_id)` - signal readiness.
- `peek()` / `release()` / `release_all()` - inspect or release departing groups.
- `cancel(group_id)` / `clear()` - withdraw waiting groups without releasing
  them; a cancelled group still leaves as a whole.
- `group_of(member)`, `groups`, `len(queue)`, `member in queue` - inspection.

Invalid operations (empty groups, duplicate group ids or members, unknown
members) raise `TitoError`.

### Complexity

For a group of `k` members, with `n` groups waiting and `m` total queued members:

- `admit()` - O(k)
- `mark_ready()` - O(1); `mark_group_ready()` - O(k)
- `peek()` - O(1) with `strict_order=True`, O(log n) amortised with
  `strict_order=False`
- `release()` - O(k) with `strict_order=True`, O(k + log n) amortised with
  `strict_order=False`
- `cancel()` - O(k) amortised; `clear()` - O(m)
- `ready_members` / `waiting_members` - O(k), since they build a new tuple

A strict-order queue always releases the head of the line, so it keeps no
ready index at all - becoming ready costs nothing in time or memory. A
non-strict queue keeps ready groups in an arrival-ordered heap, so a
long-blocked group at the head is never rescanned, and stale entries are
compacted away so the heap cannot grow without bound.

Each group stores its members once in admission order plus one hash table
carrying the per-member ready flag, so a fully ready group does not hold a
second copy of its membership. `TitoQueue` and `Group` both use `__slots__`.

### Immutability

`TitoQueue.strict_order` and `Group.sequence` are read-only: both select how
the queue indexes groups, so changing them after admission would corrupt the
release order.

### Thread safety

`TitoQueue` and `Group` are thread-safe. Every public operation is atomic, so
concurrent producers and consumers can share one queue without external
locking:

- exactly one caller ever receives a given group from `release()`, `cancel()`,
  `clear()` or `release_all()`;
- concurrent `mark_ready()` calls count each member once and notify the queue
  once, even when several threads complete the same group;
- concurrent `admit()` calls get distinct, arrival-ordered sequence numbers,
  and duplicate group ids or members are still rejected.

A queue and the groups it has admitted share one reentrant lock, so marking a
member ready and the queue bookkeeping it triggers are a single atomic step.
A group keeps that shared lock after it departs, so calls on a released group
briefly contend with its former queue.

Compound read-then-act sequences are not atomic as a whole: `peek()` followed
by `release()` may observe different groups. Use `release()` directly, or hold
your own lock around the sequence.

## Requirements

Python 3.9 or newer. No third-party dependencies.

## Tests

```bash
python -m unittest discover -s tests
```
