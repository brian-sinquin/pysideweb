# Performance baselines

Run from the repository root after installing the development environment:

```bash
uv run python benchmarks/benchmark.py --output benchmarks/results/local.json
```

The default run records cold import time; construction, serialization, wire
size, and traced memory for 100/1,000/10,000-label trees; repeated and distinct
property queues; QSS translation; and the thread count for 100 active timers.
Use `--help` to make a short smoke run or adjust sample counts.

Results include environment, commit, branch, dirty state, warmups, and samples.
Compare like-for-like environments and repeated runs. The numbers are
microbenchmarks: they do not include browser rendering or network latency.

`baseline-local.json` is the first measurement from the development workspace.
`after-timer-scheduler-local.json` records the same harness after replacing
per-timer threads: 100 timers move from 101 total threads to 2. Both are evidence
for prioritization rather than portable performance targets. The environment was
sandboxed and the worktree dirty, so future comparisons should create a clean
baseline on CI hardware before enforcing budgets.
