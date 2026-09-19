# TITO examples

Self-contained implementations of the TITO discipline in popular languages.
Each example builds a small strict-order (head-of-line FIFO) queue, admits two
groups, marks members ready one at a time, and shows that `party-1` only leaves
once *both* of its members are ready.

Every example prints exactly the same output:

```text
admit party-1: ann, bob
admit party-2: cy
ready ann
release -> waiting
ready bob
release -> party-1 [ann bob]
ready cy
release -> party-2 [cy]
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

- `admit(group_id, members)` - members enter as one group, in arrival order.
- `mark_ready(member)` - a single member signals it is ready to leave.
- `release()` - returns the head group only when *all* of its members are
  ready, so groups leave whole and in arrival order.

They deliberately leave out the features of the Python package that would
obscure the discipline itself: the non-strict ordering policy, `peek()`,
`release_all()`, `cancel()`, `clear()`, and thread safety. See the
[top-level README](../README.md) for those.
