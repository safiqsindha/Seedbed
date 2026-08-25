# Seedbed
Seeded evidence placement for reasoning benchmarks.
Seedbed scatters atomic claims across a graph of artifact slots so that the reasoning chain is maximally tangled but provably recoverable. Borrowing assumed-fill from game randomizers, it guarantees every seed is solvable, verifies it can’t be shortcut, scores its difficulty, and emits a spoiler log — so benchmarks are reproducible from a seed instead of hand-curated.

Standalone Python library: no LLM calls, no prose generation, no external services -- pure, deterministic, seeded algorithms. See `docs/PRIOR_ART_REPORT.md` for the randomizer prior art this borrows from and how its concepts map onto evidence placement.

## Quickstart

```
pip install -e .
seedbed --seed 0 --tier standard        # prints a spoiler log as JSON
python -m pytest                        # run the test suite
```

`seedbed.toyworld.build_world()` returns a hand-authored 40-slot / 8-actor / 6-claim toy world used by the test suite and the CLI's default. The library itself (`seedbed.model`, `seedbed.access`, `seedbed.fill`, `seedbed.solver`, `seedbed.cheat`, `seedbed.difficulty`, `seedbed.spoiler`) is world-agnostic -- any `World` with slots, actors, and claims works.

## Modules

- `model.py` -- `Actor`, `Claim`, `Slot`, `World` data structures.
- `access.py` -- pluggable `AccessLogic` predicate (graph reachability + authority checks) and the `EASY`/`STANDARD`/`HARD` logic tiers.
- `fill.py` -- seeded assumed fill: places claims into slots, difficulty-maximizing among legal candidates.
- `solver.py` -- the solvability oracle: fixed-point recovery of which claims are inferable from a placement.
- `cheat.py` -- cheatability check: confirms the solver fails on every proper subset of the placed chain evidence.
- `difficulty.py` -- tunable difficulty scorer (hop count, authority reversals, distractor density, low-salience carrier fraction).
- `spoiler.py` / `cli.py` -- spoiler log assembly and the `seedbed` CLI.