<div align="center">

# 🎟️ tito

**Together In Together Out** — a batch scheduling queue for groups that must stay whole.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)
[![Thread safe](https://img.shields.io/badge/thread--safe-yes-brightgreen.svg)](#-thread-safety)
[![Examples](https://img.shields.io/badge/examples-13%20languages-orange.svg)](examples/README.md)

</div>

---

Members that enter the system as a group are **never split up while they
wait**, and they only leave once *every* member of their group is ready to go.

```text
admit       ┌───────────────┐   ┌─────────┐        release
  ──────▶   │ ann ✓  bob ·  │   │  cy ✓   │   ──────────▶  whole groups only
            └───────────────┘   └─────────┘
              party-1 (waiting)  party-2 (ready)
```

## 📑 Contents

- [Install](#-install)
- [Quick start](#-quick-start)
- [Why TITO?](#-why-tito)
- [Ordering policies](#-ordering-policies)
- [API](#-api)
- [Complexity](#-complexity)
- [Immutability](#-immutability)
- [Thread safety](#-thread-safety)
- [Examples in 13 languages](#-examples-in-13-languages)
- [Requirements & tests](#-requirements--tests)
- [Further reading](#-further-reading)

## 📦 Install

TITO is not published on PyPI; install it from a checkout of this repository:

```bash
git clone https://github.com/charles2ke/tito.git
cd tito
pip install .
```

For a quick look you can also skip installing altogether and run Python from
the repository root — `tito/` is an ordinary importable package.

## 🚀 Quick start

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

No third-party dependencies, no configuration, no background threads.

## 💡 Why TITO?

[`examples/practical_usage.py`](examples/practical_usage.py) applies the real
package to five small, realistic problems — run it with
`python examples/practical_usage.py`:

| Scenario | What it shows |
| -------- | ------------- |
| 🍽️ **Restaurant waitlist** | Strict order: a party is seated only once every guest has arrived, and is never overtaken by a party that arrived later. |
| 🎮 **Matchmaking lobbies** | Relaxed order: a complete squad starts its match without waiting for an older, half-full lobby. |
| 📦 **Batch publishing** | All-or-nothing: dataset shards publish together, and a failed batch is withdrawn whole with `cancel`, so nothing partial is ever published. |
| 🧵 **Parallel fan-out** | Thread safety: workers mark their own part of a request ready; the response is assembled once all parts have landed, with no extra locking. |
| 🛡️ **Guarded admission** | Double-booking a member is refused rather than silently corrupting the group that already holds it. |

## 🔀 Ordering policies

| Policy | Behaviour |
| ------ | --------- |
| `TitoQueue(strict_order=True)` *(default)* | Head-of-line FIFO. Only the oldest waiting group may depart, so groups always exit in arrival order. |
| `TitoQueue(strict_order=False)` | Any fully ready group may depart, so a group that is still waiting does not block younger ready groups. |

## 📚 API

| Call | Purpose |
| ---- | ------- |
| `admit(group_id, members)` | Admit a group; members enter together. |
| `mark_ready(member)` / `mark_group_ready(group_id)` | Signal readiness. |
| `peek()` / `release()` / `release_all()` | Inspect or release departing groups. |
| `cancel(group_id)` / `clear()` | Withdraw waiting groups without releasing them; a cancelled group still leaves as a whole. |
| `group_of(member)`, `groups`, `len(queue)`, `member in queue` | Inspection. |

Invalid operations (empty groups, duplicate group ids or members, unknown
members, unhashable group ids or members) raise `TitoError`.

A `Group` returned by `admit()`, `release()` or `cancel()` is a plain object you can keep and inspect:

| Call | Purpose |
| ---- | ------- |
| `members`, `ready_members`, `waiting_members` | Membership in admission order. |
| `is_ready`, `ready_count` | Whether the whole group may depart, and how far along it is. |
| `sequence` | Arrival order assigned at admission. |
| `mark_ready(member)` | Mark one member ready; returns whether the group is now ready. |
| `len(group)`, `iter(group)`, `member in group` | Inspection. |

## ⚡ Complexity

For a group of `k` members, with `n` groups waiting and `m` total queued members:

| Operation | Strict order | Relaxed order |
| --------- | ------------ | ------------- |
| `admit()` | O(k) | O(k) |
| `mark_ready()` | O(1) | O(1) |
| `mark_group_ready()` | O(k) | O(k) |
| `peek()` | O(1) | O(log n) amortised |
| `release()` | O(k) | O(k + log n) amortised |
| `cancel()` | O(k) amortised | O(k) amortised |
| `clear()` | O(m) | O(m) |
| `ready_members` / `waiting_members` | O(k) | O(k) |

<details>
<summary>How the queue stays this cheap</summary>

A strict-order queue always releases the head of the line, so it keeps no
ready index at all — becoming ready costs nothing in time or memory. A
non-strict queue keeps ready groups in an arrival-ordered heap, so a
long-blocked group at the head is never rescanned, and stale entries are
compacted away so the heap cannot grow without bound.

Each group stores its members once in admission order plus one hash table
carrying the per-member ready flag, so a fully ready group does not hold a
second copy of its membership. `TitoQueue` and `Group` both use `__slots__`.

</details>

## 🔒 Immutability

`TitoQueue.strict_order` and `Group.sequence` are read-only: both select how
the queue indexes groups, so changing them after admission would corrupt the
release order.

## 🧵 Thread safety

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

> ⚠️ Compound read-then-act sequences are not atomic as a whole: `peek()`
> followed by `release()` may observe different groups. Use `release()`
> directly, or hold your own lock around the sequence.

## 🌍 Examples in 13 languages

The same discipline written from scratch in thirteen popular languages lives in
[`examples/`](examples/README.md) — C, C++, C#, Go, Java, JavaScript, Kotlin,
PHP, Python, Ruby, Rust, Swift and TypeScript. Each one implements the whole
API above, apart from thread safety, and prints the same output.

## ✅ Requirements & tests

Python 3.9 or newer. No third-party dependencies.

```bash
python -m unittest discover -s tests
```

## 📖 Further reading

- [`docs/technical-disclosure.md`](docs/technical-disclosure.md) — the
  algorithm described in detail.
- [`docs/prior-art.md`](docs/prior-art.md) — how TITO compares to known
  techniques.
