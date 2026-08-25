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

`seedbed.toyworld.build_world()` returns a hand-authored 40-slot / 8-actor / 7-claim toy world used by the test suite and the CLI's default. The library itself (`seedbed.model`, `seedbed.access`, `seedbed.fill`, `seedbed.solver`, `seedbed.cheat`, `seedbed.difficulty`, `seedbed.spoiler`) is world-agnostic -- any `World` with slots, actors, and claims works.

## Modules

- `model.py` -- `Actor`, `Claim`, `Slot`, `World`. A claim's `support` is a tuple of **alternative sufficient sets** (`requires(...)` for one conjunctive route, `either(...)` for several), so a conclusion can be established more than one way.
- `access.py` -- pluggable `AccessLogic` predicate (graph reachability + authority checks) and the `EASY`/`STANDARD`/`HARD` logic tiers.
- `fill.py` -- seeded assumed fill with **backtracking**: places claims into slots, exploring difficulty-maximizing candidates first and never placing a claim where two support alternatives are live.
- `solver.py` -- the solvability oracle: fixed-point recovery of which claims are inferable, and which are actually **load-bearing** (`SolveResult.live_route`).
- `cheat.py` -- cheatability check: confirms the solver fails on every proper subset of the *live route*.
- `difficulty.py` -- tunable difficulty scorer (hop count, authority reversals, distractor density, low-salience carrier fraction).
- `spoiler.py` / `cli.py` -- spoiler log assembly and the `seedbed` CLI.

## What is and isn't guaranteed

Worth reading before trusting a number out of this engine. Full detail, with
measurements, in [`docs/PRIOR_ART_REPORT.md` §6](docs/PRIOR_ART_REPORT.md).

**Guaranteed:**

- *Solvable.* Every placement the fill returns is verified by the reference solver.
- *Uncheatable.* No proper subset of the live route recovers the target. The fill prevents redundant support at placement time, so this is structural rather than a post-hoc filter.
- *Complete.* The fill fails only when no legal placement exists. Verified against an independent reference enumerator: 0 false negatives over 80 fillable worlds, 0 false positives over 40 impossible ones. `SearchBudgetExceeded` reports "don't know" separately from `UnsolvableWorldError`'s "proven impossible".
- *Reproducible.* Same seed, same tier, byte-identical placement and spoiler log.
- *Loud on pathology.* A support cycle, a claim no author may carry, or an unsatisfiable authority requirement raises immediately and names the claim at fault.

**Not guaranteed:**

- *Globally maximal difficulty.* The fill returns the hardest of the first `solution_limit` (default 32) complete placements — a bounded best-of-N. `FillResult.solutions_compared` reports the bound.
- *Monotone difficulty across independently generated placements.* Monotonicity holds for one fixed placement scored under each tier (0 violations / 177). Different tiers otherwise pick different support routes, so those totals are not comparable.
- *Calibrated weights.* `DEFAULT_WEIGHTS` are placeholders, not tuned against any real benchmark.