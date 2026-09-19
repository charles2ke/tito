# TITO - Prior Art Analysis

> **Status: engineering research, not legal advice and not a patent search.**
> This is a working comparison of TITO against publicly known techniques,
> assembled from the open literature. It is not a substitute for a
> professional prior-art search, and no patent numbers are asserted here
> because they have not been verified against the register. Companion
> document: [`technical-disclosure.md`](technical-disclosure.md).

## Summary

The core TITO idea - *a set admitted together is never split, and departs only
when every member is ready* - is well established in the scheduling
literature, under the names **gang scheduling**, **coscheduling**, and
**barrier synchronization**. The foundational work predates this repository by
roughly four decades.

What is less obviously covered is not the discipline but the specific
**implementation mechanisms**: the policy-driven switch between an index-free
and an indexed strategy, the lock-donation admission protocol, and the bounded
lazy readiness index. Those are where a search should concentrate.

## 1. Gang scheduling / coscheduling

**Ousterhout, J. K., "Scheduling Techniques for Concurrent Systems,"
*Proc. 3rd International Conference on Distributed Computing Systems*, 1982.**

The foundational reference. It establishes the coscheduling principle: the
processes of a parallel program form a *working set* that must be scheduled
simultaneously for the program to make progress. The "Ousterhout matrix"
(rows = time slices, columns = processors, cells = gang members) is the
classic data structure, and all members of a gang are switched in and out
**as a unit**.

**Bearing on TITO.** This directly anticipates invariants 4.1 and 4.2
(atomicity of entry and exit). The unit-of-scheduling-is-the-set idea is not
new, and any claim drafted at that level of generality should be expected to
read on this work.

Subsequent literature is extensive: implicit and dynamic coscheduling, "bag of
gangs" formulations where a set of gangs is held until all sub-gangs complete,
soft real-time gang scheduling with atomicity constraints, and modern kernel
implementations such as RT-Gang (2019) enforcing one-gang-at-a-time policies.

## 2. Barrier synchronization

A barrier holds every participant until all participants have arrived, then
releases them together. This is TITO's unanimous-readiness predicate
(invariant 4.3) in its purest form, and it is textbook material in every
parallel-computing curriculum.

**Bearing on TITO.** `mark_ready()` incrementing a counter until it equals the
group size, then releasing, *is* a counting barrier. The distinction TITO can
draw is narrow: TITO layers the barrier semantics onto a *queue of many
independent barriers* with an ordering policy between them, whereas a
classical barrier is a single rendezvous point with no queue discipline and no
inter-barrier ordering. That is a real difference, but it is a difference of
composition, not of underlying mechanism.

## 3. Batch and all-or-nothing admission

Adjacent, well-populated areas that a search will surface:

- **Transactional all-or-nothing semantics.** Two-phase commit and atomic
  transactions: every participant votes, and the batch commits only on
  unanimity. TITO's readiness voting is structurally the same shape.
- **Batch schedulers in HPC.** Slurm, PBS, LSF and similar systems allocate
  jobs as indivisible node sets, with backfill policies that are the direct
  analogue of TITO's `strict_order=False`: a job that cannot run yet does not
  block a younger job that can.
- **Kubernetes co-scheduling / "PodGroup" gang scheduling.** Modern container
  orchestration has an explicit gang-scheduling plugin in which a `PodGroup`
  is admitted only when the minimum member count can be satisfied
  simultaneously.
- **Restaurant party seating.** The everyday embodiment: a party of six waits
  as a party of six and is seated as a party of six. This matters more than it
  sounds, because it is a widely known real-world practice that an examiner
  can cite as showing the underlying idea is commonplace.

## 4. Ordering policies

- **Head-of-line blocking** (`strict_order=True`) is a named, thoroughly
  studied phenomenon in networking and switch design. Preserving strict
  arrival order at the cost of throughput is the defining trade-off of FIFO
  service, and is not novel.
- **Head-of-line bypass / backfill** (`strict_order=False`) is equally
  well known: out-of-order service in which a blocked head does not stall
  eligible successors appears throughout switch scheduling, disk I/O
  scheduling, and HPC backfill.

**Bearing on TITO.** Each policy individually is old. The candidate
distinction in the disclosure (§9a, §9b) is not the policies themselves but
that a *single primitive* selects between them at construction and, having
done so, changes its internal indexing strategy accordingly - specifically,
maintaining **no readiness index at all** under the head-of-line policy on the
ground that any such index could only describe groups the policy forbids from
departing. Whether that optimisation is independently known is the most
interesting open question in this analysis, and it is the kind of question a
professional search is equipped to answer and this document is not.

## 5. Concurrency mechanisms

TITO's §6.2 lock-donation protocol - construct an object with a private lock,
then replace that lock with the container's lock at the moment of publication,
while the object is still unreachable by other threads - is an unusual enough
manoeuvre that it did not surface in general scheduling literature. It is best
understood as a variant of lock coarsening combined with safe publication.

Similarly, §6.3's combination of a weak-referenced completion callback (to
avoid a container→element→callback→container reference cycle) with
threshold-triggered compaction of a lazy-deletion heap is standard-issue
engineering individually, but the combination applied to a readiness index is
specific.

**Bearing on TITO.** These are the strongest candidates in the disclosure
precisely *because* they are narrow and mechanical. They are also the areas
where a search is most likely to turn up software patents rather than academic
papers, and where classification-based searching (rather than keyword
searching) will be necessary.

## 6. Where to search

For a professional searcher, the relevant starting points:

**CPC classifications**
- `G06F 9/4881` - scheduling, task scheduling and dispatching
- `G06F 9/48` - program initiating and switching
- `G06F 9/50` - allocation of resources
- `G06F 9/52` - program synchronisation, mutual exclusion and semaphores
- `H04L 47/50` - queue scheduling in packet networks

**Keyword clusters**
- gang scheduling; coscheduling; co-scheduling; group scheduling
- atomic group admission; all-or-nothing scheduling; indivisible task set
- barrier synchronization; rendezvous; counting barrier
- head-of-line blocking; head-of-line bypass; backfill scheduling
- pod group; gang scheduler plugin

**Non-patent literature**
- Ousterhout 1982 and the coscheduling line of work descending from it
- Feitelson's parallel job scheduling surveys
- Slurm / PBS / LSF scheduler design documentation
- Kubernetes scheduler-plugins coscheduling design docs

## 7. Honest assessment

Taking the above together:

- The **discipline** (together in, together out) is very likely anticipated.
  Gang scheduling covers it squarely, and the restaurant analogy means an
  examiner can characterise it as a computerised version of a long-standing
  human practice - which is exactly the framing that attracts a §101
  rejection.
- The **two-policy architecture** is a plausible but uncertain distinction.
  It may be anticipated by backfill-capable batch schedulers.
- The **implementation mechanisms** (§6.2, §6.3) are the most defensible, and
  also the narrowest. A patent limited to them would be correspondingly easy
  to design around.
- Separately from novelty, the AGPL-3.0 patent grant and the existing public
  disclosure substantially limit what enforcement value a grant would carry.
  See `technical-disclosure.md` §11.

The practical recommendation in the disclosure stands: commission a
professional search before committing to a filing. It is the cheapest step and
the most likely to be decisive.
