# TITO examples

Two kinds of example live here:

- [`practical_usage.py`](practical_usage.py) - realistic uses of the real
  `tito` package: *when* and *why* to reach for a TITO queue.
- `tito_example.*` - self-contained reimplementations of the whole API in
  thirteen languages, all printing the same API tour.

## Practical usages

[`practical_usage.py`](practical_usage.py) uses the installed package (or a
plain checkout) to solve five small, realistic problems:

| Scenario | Discipline it shows |
| -------- | ------------------- |
| Restaurant waitlist | strict order: a party is seated whole, and never overtaken by a later party |
| Matchmaking lobbies | relaxed order: a complete lobby starts without waiting for an older, half-full one |
| Batch publishing | all-or-nothing: every shard publishes together, and `cancel` rolls back the whole batch |
| Parallel fan-out | thread safety: workers mark their own part ready, the request is answered once all parts land |
| Guarded admission | invalid work is refused instead of corrupting a queued group |

```bash
python examples/practical_usage.py
```

It prints, from the repository root:

```text
-- restaurant seating (strict order) --
ready to seat: None
still waiting on: ['priya']
seat mehta-party: asha raj priya
seat okafor-party: ngozi chidi
parties left on the waitlist: 0

-- matchmaking lobbies (relaxed order) --
start match: lobby-beta ['hedy', 'alan']
alpha still loading: ['linus', 'grace']
start match: lobby-alpha ['ada', 'linus', 'grace']
lobbies waiting: 0

-- batch publishing (all-or-nothing) --
publish 2026-09-18: 3 shards
rolled back 2026-09-19, 2/3 shards computed
nothing half-published: True

-- parallel fan-out (thread-safe) --
respond to request-7 with 3 parts: orders-data profile-data recommendations-data

-- guarded admission --
refused: members already in the queue: ['nurse-2']
shift-a intact: ['nurse-1', 'nurse-2']
```

`tests/test_practical_usage.py` runs every scenario, so the code above stays
honest.

## API tour, in thirteen languages

Self-contained implementations of the TITO discipline in popular languages.
Each example implements the whole `TitoQueue` and `Group` API and runs the same
four-part demo: strict (head-of-line FIFO) ordering, relaxed ordering,
withdrawing groups with `cancel`/`clear`, and the errors that guard the TITO
invariants.

Every example prints exactly the same output:

```text
-- strict order --
admit party-1 [ann bob]
admit party-2 [cy]
len 2, groups party-1 party-2
contains ann true, contains zoe false
group_of bob -> party-1
party-1: size 2, contains ann true, contains zoe false
mark_ready ann -> group ready false
party-1: 1/2 ready [ann] waiting [bob] is_ready false
peek -> waiting
release -> waiting
party-1.mark_ready bob -> group ready true
party-1: 2/2 ready [ann bob] waiting [] is_ready true
peek -> party-1 [ann bob]
release -> party-1 [ann bob]
mark_group_ready party-2 -> true
release_all -> party-2 [cy]
len 0

-- relaxed order --
strict_order false
admit party-3 [dee eli]
admit party-4 [fay]
mark_group_ready party-4 -> true
peek -> party-4 [fay]
release -> party-4 [fay]
mark_ready dee -> group ready false
release -> waiting
mark_ready eli -> group ready true
release_all -> party-3 [dee eli]
len 0

-- cancel and clear --
admit party-5 [gil hal]
admit party-6 [ivy]
admit party-7 [jay]
mark_ready gil -> group ready false
cancel party-5 -> party-5 [gil hal] 1/2 ready
groups party-6 party-7
clear -> party-6 [ivy], party-7 [jay]
len 0, contains ivy false

-- errors --
admit party-8 [kim]
admit party-8 [kim] -> group party-8 is already in the queue
admit party-9 [] -> group party-9 must contain at least one member
admit party-9 [jay jay] -> group party-9 contains duplicate members
admit party-9 [kim] -> members already in the queue: kim
mark_ready zoe -> zoe is not in the queue
party-8.mark_ready zoe -> zoe is not a member of group party-8
mark_group_ready party-9 -> group party-9 is not in the queue
cancel party-9 -> group party-9 is not in the queue
```

The examples depend only on their language's standard library, so none of them
needs the Python package installed - `examples/tito_example.py` is the one that
mirrors the real [`TitoQueue`](../tito/tito.py) API most closely.

## Running them

| Language   | File | Command |
| ---------- | ---- | ------- |
| C          | [`tito_example.c`](tito_example.c) | `gcc -std=c11 -O2 -o /tmp/tito_c examples/tito_example.c && /tmp/tito_c` |
| C++        | [`tito_example.cpp`](tito_example.cpp) | `g++ -std=c++17 -O2 -o /tmp/tito_cpp examples/tito_example.cpp && /tmp/tito_cpp` |
| C#         | [`csharp/TitoExample.cs`](csharp/TitoExample.cs) | `dotnet run --project examples/csharp` |
| Go         | [`tito_example.go`](tito_example.go) | `go run examples/tito_example.go` |
| Java       | [`TitoExample.java`](TitoExample.java) | `javac -d /tmp/tito examples/TitoExample.java && java -cp /tmp/tito TitoExample` |
| JavaScript | [`tito_example.js`](tito_example.js) | `node examples/tito_example.js` |
| Kotlin     | [`tito_example.kt`](tito_example.kt) | `kotlinc examples/tito_example.kt -include-runtime -d /tmp/tito.jar && java -jar /tmp/tito.jar` |
| PHP        | [`tito_example.php`](tito_example.php) | `php examples/tito_example.php` |
| Python     | [`tito_example.py`](tito_example.py) | `python examples/tito_example.py` |
| Ruby       | [`tito_example.rb`](tito_example.rb) | `ruby examples/tito_example.rb` |
| Rust       | [`tito_example.rs`](tito_example.rs) | `rustc -O -o /tmp/tito_rust examples/tito_example.rs && /tmp/tito_rust` |
| Swift      | [`tito_example.swift`](tito_example.swift) | `swift examples/tito_example.swift` |
| TypeScript | [`tito_example.ts`](tito_example.ts) | `tsc --strict --target es2020 --outDir /tmp/tito examples/tito_example.ts && node /tmp/tito/tito_example.js` |

Run every command from the repository root.

## What the examples cover

Every method of the package's public API:

- `admit(group_id, members)` - members enter as one group, in arrival order.
- `mark_ready(member)` / `mark_group_ready(group_id)` - signal readiness;
  marking a member reports whether its whole group has become ready.
- `peek()` / `release()` / `release_all()` - a group is only ever handed back
  when *all* of its members are ready, so groups leave whole and in order.
- `cancel(group_id)` / `clear()` - withdraw waiting groups; a cancelled group
  still leaves as a whole, ready or not.
- `group_of(member)`, `groups`, queue length and membership tests.
- On a group: `members`, `ready_members`, `waiting_members`, `ready_count`,
  `is_ready`, `mark_ready(member)`, size and membership tests.
- Both ordering policies: strict order (head-of-line FIFO, the default), and
  relaxed order, where a ready group is not held up by an older group that is
  still waiting.
- The errors that invalid operations report: empty groups, duplicate group ids
  or members, and unknown members or groups.

They deliberately leave out the parts of the Python package that are about
performance and concurrency rather than the discipline itself: the package
indexes ready groups in an arrival-ordered heap and is thread-safe, while the
examples just scan the waiting groups in arrival order and assume a single
thread. See the [top-level README](../README.md) for those.
