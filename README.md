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

### Ordering policies

- `TitoQueue(strict_order=True)` (default): head-of-line FIFO. Only the oldest
  waiting group may depart, so groups always exit in arrival order.
- `TitoQueue(strict_order=False)`: any fully ready group may depart, so a group
  that is still waiting does not block younger ready groups.

### API

- `admit(group_id, members)` - admit a group; members enter together.
- `mark_ready(member)` / `mark_group_ready(group_id)` - signal readiness.
- `peek()` / `release()` / `release_all()` - inspect or release departing groups.
- `group_of(member)`, `groups`, `len(queue)`, `member in queue` - inspection.

Invalid operations (empty groups, duplicate group ids or members, unknown
members) raise `TitoError`.

### Complexity

For a group of `k` members:

- `admit()` - O(k)
- `mark_ready()` - O(1) amortised; `mark_group_ready()` - O(k)
- `peek()` / `release()` - O(1) amortised in both ordering modes
- `ready_members` / `waiting_members` - O(k), since they build a new tuple

Groups that become ready are tracked in an arrival-ordered index, so a
long-blocked group at the head of a non-strict queue is never rescanned.

## Tests

```bash
python -m unittest discover -s tests
```
