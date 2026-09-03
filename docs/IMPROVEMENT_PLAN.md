# Package improvement plan

Prepared 2026-09-02 against main `95a0adf`, plus the runtime integration fixes in
this working branch. This is an ordered engineering backlog, not a promise of
measured speedups. Keep the pure-Python/no-Qt install and existing Qt import API.

## Completed in this change

- Replaced the disconnected experimental runtime with compatibility exports from
  the canonical core and state modules, eliminating duplicate behavior/state.
- Repaired JSON encoding, Qt Property descriptors, bound-method disconnect, and
  concurrent signal sender tracking.
- Wired conservative QSS handling and WebSocket validation into actual paths.
- Fixed the application stylesheet protocol mismatch and explicit full resync.
- Coalesced pending changes at enqueue, removed listener calls under the registry
  lock, and confined debounce decisions to the server loop.
- Added behavioral, real HTTP/WebSocket, and JavaScript protocol tests; corrected
  contributor instructions and documented compatibility/security boundaries.
- Added a Chromium end-to-end suite for the four demos and critical runtime
  behavior, fixed pre-render update ordering, and removed the external font fetch.
- Added a versioned JSON benchmark harness and recorded the first local baseline.
- Removed dead renderer state, duplicate factories/updaters and no-op wrappers;
  shared text-control and painting fallback implementations. The renderer is
  roughly 370 lines shorter than before this cleanup, without minification.
- Fixed tab/stack page-growth loops and added DOM lifecycle regression tests.
- Added independent bounded client outboxes, lazy resync after overflow,
  send/close deadlines, and writer cleanup on disconnect/server shutdown.
- Added `examples/showcase.py`: six interactive sections covering all 26 renderer
  widget types, with a coverage guide, callback tests, two-client WebSocket
  round trip/reconnect, and a CI browser walkthrough. Fixed the textarea update
  field, root QObject property registration, nested page counting and decimal
  spin-button steps exposed by the example.

## Recommended order

| Priority | Area | Work | Completion evidence |
| --- | --- | --- | --- |
| P0 | Correctness and measurement | **Implemented; awaiting CI Chromium execution.** Keep the browser suite and reproducible performance baseline current. | Demos run in Chromium; input, focus, style changes, painting, reconnect, disposal and pre-render ordering assertions pass; benchmark JSON records environment and commit. |
| P0 | Security | Design authenticated network mode, exact configured origins/hosts, per-user connection limits and session authorization. Keep local mode simple. | Unauthorized clients cannot read trees or dispatch events; cross-origin, rebinding, expired-session, and reconnect-abuse tests pass. |
| P1 | Performance | **Bounded outboxes implemented.** Measure healthy-client p95 latency and aggregate memory with real stalled sockets at 1/10/50 clients. | Deterministic isolation/overflow/timeout tests pass; real-network latency and memory budgets remain to be measured. |
| P1 | Correctness and performance | **Timer scheduler implemented.** Continue defining single-owner event dispatch beyond timers. | Deterministic stop/restart/single-shot tests pass; 100 active timers use one extra thread; serialized callback behavior is documented. |
| P1 | Optimization | Cache translated QSS and serialized unchanged subtrees with explicit invalidation. Measure before adding complexity. | Repeated unchanged serialization avoids repeated translation/painting; state/property/layout invalidations remain correct. |
| P1 | Compact code | **First consolidation pass complete.** Split core by cohesive responsibilities and renderer by widget families only where it improves maintenance; retain stable exports. | Shared factories/properties/fallbacks pass regression tests; no second runtime or generated fallback that silently changes supported behavior. |
| P2 | Features | Implement QAbstractItemModel-backed QTableView/QTreeView with virtualized rows. | Large datasets render only visible rows; selection/editing/model-change signals match reference examples. |
| P2 | Features | Add QToolButton, date/time controls, keyboard navigation, accessibility semantics, and a capability report for unsupported APIs. | Widget behavior, keyboard interactions, focus order, and supported Qt overloads covered in browser and Python tests. |
| P2 | Packaging | Build/test wheel contents, install examples against the wheel, add release automation and a compatibility matrix. | Fresh installs contain all static assets; supported Python versions pass; release/version/changelog agree. |
| P3 | Architecture | Introduce explicit application/session contexts before multi-user isolation. | Two sessions have separate widget trees, settings scope, and event authorization; existing single-app behavior remains supported. |

## Benchmark design and decision gates

Create a small versioned harness using perf_counter, tracemalloc, and browser
performance timings. Record Python/browser versions, hardware, warmup, sample
count, median and p95. Run cold import and startup in fresh processes; keep network
and browser timing separate from Python serialization time.

| Scenario | Measure | Decision enabled |
| --- | --- | --- |
| 100 / 1,000 / 10,000 widgets | Construction, full-tree serialization, wire bytes, browser render time, peak memory | Subtree caching, virtualized views, structural diffs |
| Repeated writes to one property vs many properties | Pending entries, enqueue/drain time, bytes per update | Queue behavior and compact wire encoding |
| 100 Hz slider/timer updates | End-to-end p50/p95 latency, coalescing ratio, CPU | Debounce interval and client input coalescing |
| 1 / 10 / 50 connected clients, one stalled | Healthy-client p95 latency and queue memory | Backpressure and client isolation |
| 1 / 100 / 1,000 timers | Thread count, CPU, jitter, shutdown latency | Shared scheduler |
| Repeated create/show/delete cycles | Registry size, retained objects, memory after GC | Ownership and disposal fixes |
| Painted widgets and repeated identical QSS | Paint/translation call counts and frame time | Caching and invalidation policy |

Use baseline-relative budgets initially: flag a sustained >10% median/p95
regression over repeated samples for investigation, rather than failing CI on a
single noisy sample. Set absolute latency/memory budgets after collecting data.
Any optimization must preserve the behavioral corpus and show a reproducible gain
in its target scenario. Do not trade away Qt semantics merely to reduce lines.

## Security work that remains

The current same-origin/Host checks, message bounds, and conservative stylesheet
policy narrow the attack surface but are not a multi-user security model.

1. Specify local vs authenticated remote mode. Origin is browser protection, not
   proof of identity. Do not put shared secrets into frontend source or URLs.
2. Add per-widget event allowlists and semantic value validation (ranges, types,
   indexes, enabled state), not just an envelope check.
3. Add limits across connections and per identity; the current per-connection
   limiter resets on reconnect. Size total connections and outbound resources.
4. Audit rich-text sanitization with an adversarial browser corpus and define
   which external image/link schemes are allowed. JSON escaping does not make
   HTML safe after decoding.
5. Define reverse-proxy trust explicitly: exact allowed origins/hosts, TLS/WSS,
   forwarded-header handling only from trusted proxies, and deployment examples.
6. Add structured security logging without payloads/secrets, dependency auditing,
   and private vulnerability reporting. Test server startup failures, cancellation,
   clean shutdown/restart, and listener cleanup.

These priorities follow the primary
[OWASP WebSocket Security guidance](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
on Origin checks, authentication, input limits, and backpressure. The concrete
ordering above reflects this repository's shared registry and server design.

## Code consolidation rules

Keep `core_refactored` and `state_refactored` only as small compatibility facades
until a documented removal release; do not start another parallel refactor.
Extract coherent implementations (signals/properties, values/enums, application,
timers) behind the existing imports. Preserve cheap import startup and avoid
adding framework dependencies solely to reorganize code. If CSS coverage expands,
replace the conservative whole-sheet rejection policy with a real parser and an
explicit supported policy, not a growing list of regex exceptions.

## Next three follow-up changes

1. **Browser and transport measurement:** execute the existing Chromium suite in
   CI and measure real-network latency/memory with stalled clients; publish clean
   benchmark data before setting budgets. The local DOM fixture is not a browser.
2. **Remote-mode security design and implementation:** session auth, explicit
   proxy/origin configuration, semantic event checks, and limits across reconnects.
3. **Large-data performance and features:** model-backed virtualized table/tree
   views; then evaluate subtree caching against measured invalidation costs.

The first baseline makes the next engineering choices clearer: 100 active timers
create 100 additional threads; a 10,000-label full tree takes a median 243 ms to
construct and 372 ms to serialize, produces 3.30 MB of JSON, and peaks near
30.4 MB of traced Python allocations. Ten thousand repeated writes to one
property correctly collapse to one 64-byte queued update; ten thousand distinct
properties retain ten thousand updates and produce roughly 668 KB. QSS
translation takes about 76 ms for 10,000 scoped translations and is not the first
optimization target. These are local dirty-worktree Python 3.12 measurements,
not cross-machine budgets; see `benchmarks/results/baseline-local.json`.

The shared timer scheduler was implemented immediately after that baseline: the
same 100-timer benchmark now moves from 101 total threads to 2, while the
10,000-widget serialization median remains within noise (372 ms before, 366 ms
after). Bounded transport queues are now implemented; prioritize their network
measurements and virtualized model views ahead of QSS caching or cosmetic widget
breadth. Re-run on clean CI hardware
before setting regression thresholds.


## Verification of the current fixes

Local Python 3.12 run: 196 tests passed, including real aiohttp HTTP/WebSocket
exchanges, showcase callbacks and deterministic slow-client outbox tests. Eleven Node renderer tests
passed, Ruff passed, JavaScript files
passed syntax checks, and git diff whitespace checks passed. Existing CI covers
Python 3.10–3.13; remote CI results are not included in this local verification. The new
Chromium suite is configured in CI but could not run locally because this
workspace has no browser binary. Real-Qt crosschecks were not run locally.

The full local microbenchmark completed with seven measured samples and two
warmups at 100/1,000/10,000 widgets. It does not measure browser rendering or
network latency, and its dirty-worktree results are evidence rather than budgets.
