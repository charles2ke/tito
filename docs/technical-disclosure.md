# TITO - Technical Disclosure

> **Status: engineering document, not legal advice.** This file describes the
> TITO algorithm in the form an attorney or examiner would find useful as
> input. It makes no claim that any part of TITO is patentable. See
> [`prior-art.md`](prior-art.md) for the known art, and the caveats at the end
> of this document.

## 1. Title

Together In Together Out (TITO): a group-atomic queueing discipline with
selectable head-of-line and non-blocking ordering policies.

## 2. Field

Scheduling and queueing. Specifically, the management of a waiting line whose
unit of admission and unit of departure is a *group* of members rather than an
individual member.

## 3. Problem addressed

Conventional queues (FIFO, priority, fair-queueing) treat the individual item
as the atomic unit. Many real systems instead admit a set of participants that
must not be separated:

- a restaurant party that must be seated at one table at one time;
- a set of co-dependent tasks that are useless unless all of them run;
- a cohort of clients waiting on a shared resource that must be handed over as
  a unit;
- a batch of records that must commit together or not at all.

Implementing this on top of a conventional queue is normally done ad hoc per
application: some external bookkeeping counts how many members of a set have
signalled readiness, and some external policy decides when the set may leave.
The ad hoc version is where the bugs live - partial release, double release,
lost members, and unbounded growth of the readiness index.

TITO packages the discipline as a reusable primitive with explicit invariants.

## 4. The discipline (invariants)

For a queue Q holding groups G1..Gn:

1. **Group atomicity on entry.** `admit(group_id, members)` inserts all members
   as one indivisible unit. Members cannot be added to a group after admission.
2. **Group atomicity on exit.** A group departs as a whole or not at all. There
   is no operation that removes a strict subset of a group's members.
3. **Unanimous readiness.** A group is eligible to be released only when every
   one of its members has been marked ready.
4. **Uniqueness.** A member belongs to at most one group in the queue at a
   time; a group id appears at most once.
5. **Single release.** A group that has been released is removed from every
   index, so no second release of the same group can occur even under
   concurrent callers.
6. **Cancellation is the only exception to (3), never to (2).** `cancel()`
   withdraws one group and `clear()` bulk-cancels all waiting groups, including
   groups that are not fully ready; both withdraw groups whole.

Violations raise `TitoError` rather than silently degrading.

## 5. Ordering policies

The characteristic feature of TITO is that the readiness predicate (4.3) is
separated from the *ordering policy*, and the implementation switches its
indexing strategy based on which policy is selected at construction time.

### 5.1 `strict_order=True` (head-of-line FIFO)

Only the oldest waiting group may depart. A younger group that becomes ready
first still waits. Guarantees: departure order is exactly arrival order.

Because only the head can ever be the answer, the implementation keeps **no
readiness index at all**. `peek()` inspects the head of an insertion-ordered
map and tests its readiness in O(1). Tracking which younger groups are ready
would cost time and memory for information that is never read.

### 5.2 `strict_order=False` (non-blocking)

Any fully ready group may depart; a not-yet-ready group does not block younger
ready groups. Among ready groups, arrival order is still respected.

Here the implementation maintains a readiness index: a min-heap of arrival
sequence numbers plus a sequence→group map, populated lazily by a callback
fired at the moment a group's readiness count reaches its size.

### 5.3 Why the switch matters

The same public API yields two different asymptotic profiles, and the cheaper
profile pays nothing for machinery the policy cannot use. The policy is fixed
at construction and exposed read-only, so the indexing strategy and the
observable ordering can never disagree.

## 6. Data structures

For the reference Python implementation (`tito/tito.py`):

| Structure | Purpose |
| --- | --- |
| `OrderedDict[group_id -> Group]` | Waiting groups in arrival order; head lookup and removal are O(1). |
| `Dict[member -> group_id]` | Member index, giving O(1) `group_of()` and O(1) duplicate detection at admission. |
| `Group._ready: Dict[member -> bool]` | Single dict serving both membership test and ready flag. |
| `Group._ready_count: int` | Counter compared against group size; makes the unanimity test O(1) instead of O(k). |
| `_ready_heap: List[int]` + `_ready_groups: Dict[int, Group]` | Non-strict policy only: lazily populated readiness index keyed by arrival sequence. |

Three implementation details are worth calling out as the non-obvious parts:

1. **Fused membership-and-readiness map.** `_ready` replaces the conventional
   pair of sets ("all members", "ready members"). A fully ready group under the
   two-set scheme stores every member twice; the fused dict stores each member
   once and carries the flag in the same slot, while still answering membership
   in O(1).

2. **Lock donation on admission.** A `Group` is constructed with its own
   reentrant lock, outside the queue lock, because validating members can run
   arbitrary user code (hashing, iterating the `members` argument). On
   admission - while the group is still unpublished and therefore unreachable
   by any other thread - the queue *replaces* the group's lock with its own.
   From that point on, marking a member ready and the queue bookkeeping that
   readiness triggers happen under one lock as a single atomic step. This
   removes the lock-ordering problem between group and queue without forcing
   validation to run under the queue lock.

3. **Weak-referencing readiness callback with heap compaction.** The group's
   readiness callback holds only a weak reference to the queue, so the
   queue→group→callback→queue cycle does not keep discarded queues (and every
   group in them) alive until the cyclic collector runs. Separately, because
   `peek()` only discards stale heap entries when they surface at the top, the
   heap is compacted whenever it exceeds `2 * |ready_groups| + 8` entries. This
   bounds the readiness index against the workload where groups become ready
   and are then cancelled repeatedly, which would otherwise grow the heap
   without limit.

## 7. Operations and complexity

For a group of `k` members, `n` groups waiting, `m` total queued members:

| Operation | `strict_order=True` | `strict_order=False` |
| --- | --- | --- |
| `admit(group_id, members)` | O(k) | O(k) |
| `mark_ready(member)` | O(1) | O(1) amortised |
| `mark_group_ready(group_id)` | O(k) | O(k) amortised |
| `peek()` | O(1) | O(log n) amortised |
| `release()` | O(k) | O(k + log n) amortised |
| `release_all()` | O(total released) | O(total released + log n per group) |
| `cancel(group_id)` | O(k) amortised | O(k) amortised |
| `clear()` | O(m) | O(m) |
| `group_of(member)`, `len()`, `in` | O(1) | O(1) |

## 8. Operational sequence (worked example)

```
admit("party-1", ["ann", "bob"])   -> group at sequence 0
admit("party-2", ["cy"])           -> group at sequence 1
mark_ready("ann")                  -> False   (1 of 2)
mark_ready("cy")                   -> True    (party-2 complete)
release()   strict_order=True      -> None    (head party-1 not ready)
release()   strict_order=False     -> party-2 (head does not block)
mark_ready("bob")                  -> True    (party-1 complete)
release()                          -> party-1
```

The two policies diverge at exactly one line, which is the point of separating
the readiness predicate from the ordering policy.

## 9. Candidate points of distinction

Offered as *candidates* only, for an attorney to evaluate against a
professional search. None of these is asserted to be novel.

- **(a)** A single queue primitive in which the unanimous-readiness release
  predicate is decoupled from the ordering policy, with the policy selecting
  between an index-free head-of-line strategy and a sequence-keyed readiness
  index.
- **(b)** Eliminating the readiness index entirely under the head-of-line
  policy, on the ground that the index can only ever describe groups that the
  policy forbids from departing.
- **(c)** The lock-donation admission protocol of §6.2, which makes
  "mark member ready" and the queue-level bookkeeping it triggers atomic under
  a single lock without performing user-supplied validation under that lock.
- **(d)** The bounded lazy readiness index of §6.3: weak-referenced completion
  callback plus threshold-triggered heap compaction, which keeps the
  cancellation-heavy workload from growing the index without bound.
- **(e)** Cancellation as the sole, explicitly-scoped exception to unanimous
  readiness that nonetheless preserves group atomicity.

Realistically, (a) and (b) are policy/architecture observations that a search
may well find anticipated (see `prior-art.md`). (c) and (d) are concrete
implementation mechanisms and are the more defensible candidates, though they
are also the narrower ones.

## 10. Reference implementation and public disclosure

- Canonical implementation: `tito/tito.py` (Python), 374 lines.
- Thirteen from-scratch implementations of the same discipline in C, C++, C#,
  Go, Java, JavaScript, Kotlin, PHP, Python, Ruby, Rust, Swift and TypeScript
  live in `examples/`, all producing byte-identical output.
- Test suite: `tests/test_tito.py`, run with
  `python -m unittest discover -s tests`.
- **The work is publicly disclosed.** It is published on GitHub under
  AGPL-3.0. The repository's first commits are dated 2026-09-19; the git
  history is the contemporaneous record of conception and reduction to
  practice.

## 11. Caveats an attorney will raise immediately

These are flagged here so they are not a surprise later. They are engineering
observations about legal risk, not legal advice.

1. **Public disclosure has already occurred.** Most jurisdictions outside the
   US (EPC states, China, and others) apply *absolute novelty*: a pre-filing
   public disclosure is itself prior art against your own application. The US
   provides a 12-month grace period from first public disclosure. The date in
   §10 therefore starts a clock. This is the single most time-sensitive item.

2. **Subject-matter eligibility.** In the US, a queueing algorithm claimed as
   such is a strong candidate for rejection under 35 U.S.C. §101
   (*Alice/Mayo*) as an abstract idea. Claims generally need to recite a
   specific technical improvement to the operation of a computer system. Items
   (c) and (d) in §9 - concurrency control and bounded memory behaviour - are
   the material most likely to support that framing; items (a) and (b) are the
   least. The EPO applies its own technical-character requirement, which
   similarly disfavours a pure scheduling abstraction.

3. **AGPL-3.0 grants a patent licence.** Section 11 of the AGPL-3.0 conveys an
   express, royalty-free patent licence from each contributor to each
   recipient, covering claims that would be infringed by the contribution as
   conveyed. A granted patent would therefore not be enforceable against users
   of the released code. Any enforcement value would lie only outside what has
   already been conveyed - which, given §10, is not much.

4. **Prior art is substantial.** Gang scheduling and coscheduling literature
   dating to 1982 covers atomic group admission and release directly. See
   [`prior-art.md`](prior-art.md).

5. **Inventorship is a legal determination.** Under US law inventors must be
   natural persons, and inventorship is determined by contribution to the
   conception of the claimed invention - not by commit count. Portions of this
   repository's history were produced with AI assistance, which raises a
   question your attorney will need to address directly.

## 12. Next steps if pursued

1. Commission a professional prior-art search before anything else. A search
   costing a fraction of a filing may end the question outright.
2. If the search survives, a US provisional application is the low-cost way to
   preserve a priority date while the above is evaluated.
3. Bring this document, `prior-art.md`, and the full git history to a
   registered patent attorney or agent. Ask specifically about §11 items 1, 2
   and 5 - they are the items most likely to be dispositive.
