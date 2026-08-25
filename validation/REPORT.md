# Difficulty validation: report

Attempts to establish, empirically, whether `difficulty` (with
`DEFAULT_WEIGHTS`) predicts how hard a seed actually is for a model to
solve. Short answer: **inconclusive, for a specific and reportable
reason** — the solver-under-test available in this environment is at
ceiling across nearly the whole difficulty range these two bundled worlds
can produce. That is itself a finding, not a null result to bury.

## 1. What was built

`validation/` (outside `seedbed/`, per its no-LLM-calls non-goal):

- `facts.py` — renders a placement as structured facts: actors+roles,
  claims (id, target flag, min_role, eligible_authors, support
  alternatives), slots (id, author, claims carried), and the directed
  access-edge list. No labels, no salience, no timestamps — nothing
  `seedbed.solver.solve` doesn't itself consult once the adjacency graph
  is built.
- `oracle.py` — ground truth, straight from `seedbed.solver.solve`.
- `scoring.py` — binary target-recovered match, plus precision/recall/F1
  of the model's claimed supporting-chain set against the true live route.
- `prompt.py` — the fixed instruction text (a plain-English transcription
  of the solver's fixed-point rule) + facts JSON.
- `build_tasks.py` — generates the task set, deterministically.
- `analyze.py` / `spurious.py` — ingest answers, score, correlate.
- `tests/test_harness.py` — 8 tests on the harness logic itself (facts
  round-trip, oracle agreement, scoring edge cases, the ablation
  invariant), all passing, run before any model call was made.

**The one asymmetry worth naming**: the model is handed the adjacency
graph pre-built rather than the raw slot metadata (timestamp/thread/
meeting/audience) that produced it. It is not asked to re-derive
connectivity rules — it is asked to do the fixed-point recovery, which is
what `difficulty`'s terms actually score. This matches "no more than the
solver gets": `solve()` never looks at that raw metadata either, once
`build_adjacency` has run.

**The one compromise worth naming**: the solver-under-test in this
session is Claude, run as a subagent, instructed not to use code execution
("solve this yourself, don't write a script"). That instruction was
followed in every run inspected, but it is a soft constraint, not a
sandboxed one — a true black-box eval would remove Bash/Python tool access
entirely rather than ask the model to abstain. No external model API was
reachable from this environment (no key, no `anthropic` package), so
Claude is the only model this study could put under test. A result that
generalizes across model families is future work, not this session's.

## 2. Study design

- Both bundled worlds (`toy`, `relay`) × all three tiers (`easy`,
  `standard`, `hard`) = 6 buckets.
- Per bucket: tried seeds 0–59, kept 6 spread evenly across the observed
  difficulty range (not just extremes) → **36 seeds**.
- 3 independent attempts per seed (separate subagent invocations, no
  shared context) → **108 main-study answers**.
- Spurious-success check: 12 seeds (every 3rd, stratified by difficulty)
  ablated by dropping one non-target live-route claim each; Seedbed's own
  uncheatability guarantee means every one of these is unsolvable by
  construction (verified: all 12 came back `solved: false` from the
  oracle). 2 attempts each → **24 ablated-placement answers**.
- **132 model calls total**, all cached to disk under `validation/data/`
  and re-analyzable without re-spending. This is a modest-scale pilot, not
  a large eval — orchestration in this session went through individual
  agent dispatches (no bulk LLM API), which caps what's practical in one
  sitting. Scaling up is mechanical: re-run `build_tasks.py` with a larger
  `SEEDS_TO_KEEP` and more attempt rounds.

## 3. Correlation: difficulty vs. recovery accuracy

**n = 36 seeds, Pearson r = 0.19, Spearman r = 0.22** (95% CI on Pearson,
Fisher z: **[-0.15, 0.48]** — contains zero; not statistically
distinguishable from no correlation at this n). Mean chain-F1 correlates
identically to binary accuracy in this sample (see §5).

This is far below TRACE's r ≈ -0.96, and the sign is even in the
"wrong" direction if you squint (weak positive rather than negative —
harder-scored seeds trending very slightly *more* often solved). **The
honest reason is a ceiling effect, not a disproof of the metric:**

```
accuracy distribution across 36 seeds: 32 at 1.00, 4 at 0.67, 0 elsewhere
difficulty range tested:                7.33 -- 35.20
max difficulty observed in 150 seeds/bucket (both worlds, all tiers): 35.4
```

The 7.3–35.2 range tested is essentially the *entire* difficulty range
these two bundled worlds can produce at all (confirmed by re-sampling 150
seeds per bucket: relay/standard tops out at 35.4, toy tops out at 29.75).
Across that whole range, Claude recovered the target correctly in **32/36
seeds at 100% (3/3 attempts)**, and never below 67%. There is no headroom
left in these worlds to see whether accuracy would fall off at "harder
than anything these worlds can generate" — the ceiling isn't a sampling
artifact of this study, it's a property of the current worlds relative to
this solver.

Per-tier accuracy: `easy` 88.9%, `standard` 100%, `hard` 100% — i.e. the
*least* strict tier has the *lowest* accuracy in this sample, which is
backwards from what tier-strictness-as-difficulty-proxy would predict, and
is driven entirely by one cluster (next section), not a tier-wide effect.

**Where the correlation could not be tested**: whether `difficulty`
predicts accuracy *above* ~35 (these worlds' ceiling) is simply unanswered
here. A larger/deeper world (more slots, longer chains, more stacked
authority gates) would be needed to find out.

## 4. Per-term breakdown

| term | n | Pearson | Spearman |
|---|---|---|---|
| `authority_reversals` | 36 | **0.66** | 0.66 |
| `low_salience_fraction` | 36 | 0.06 | -0.01 |
| `hop_count` | 36 | 0.05 | 0.07 |
| `distractor_density` | 36 | -0.02 | -0.03 |

`authority_reversals`'s 0.66 looks like the standout, but treat it as a
confound, not a term worth weighting up: in this sample it only ever takes
values 0 or 1 (8 seeds at 0, 28 at 1), and **all four of the accuracy-0.67
seeds happen to be the ones with `authority_reversals = 0`** — but so do 4
*other* seeds that scored 100%. The four misses are also the same
`relay/easy` seeds discussed below, i.e. the correlation is standing in
for a `world × tier` effect it happens to line up with, not a
term-specific difficulty signal. `hop_count`, `distractor_density`, and
`low_salience_fraction` show no signal at all in this sample (all
|r| < 0.1) — but that is exactly what you'd expect under a ceiling effect
regardless of whether those terms carry real signal, so this is not
evidence they're decoration. It's evidence this study can't see their
signal yet.

## 5. What actually went wrong on the 4 non-perfect seeds

All four are `relay/easy` (difficulty 16.25–25.0), all from the **same**
subagent batch call (the round-2 dispatch covering `relay_easy`'s six
seeds). Two other seeds in that identical batch (`relay_easy_017`,
`relay_easy_031`) were answered correctly. The failing attempts didn't
produce a wrong chain — they answered `{"target_known": false, "chain":
[]}`, a clean miss rather than a near-miss. Because `mean_f1` only scores
attempts where the model claimed success, and every "claimed success"
attempt in the whole 108-answer main study had a perfectly-matching chain
(F1 = 1.0 whenever `target_known` was correctly `true`), **binary accuracy
and chain-F1 are identical in this sample** — no case of "right answer,
wrong reasoning" was observed. That's a real, if narrow, positive result:
when this solver says it recovered the target, its stated chain matched
the live route every single time in 104 successful attempts.

The clustering by batch (not by seed difficulty) is itself informative for
anyone repeating this study: some of what looks like seed-to-seed
variance may be attempt-to-attempt / dispatch noise rather than a
difficulty gradient, which is exactly why the harness runs multiple
independent attempts per seed rather than trusting any single one.

## 6. Spurious success check

**0 / 24 (0%) spurious successes** — every one of the 12 ablated
placements (each missing exactly one live-route claim, guaranteed
unsolvable by Seedbed's own uncheatability property) was correctly
reported as unrecoverable, across both attempts on each. Clopper-Pearson
95% upper bound on the true rate: **14.2%**.

This is a real result, not "no data": it's the opposite of TRACE's ~28%
reported rate for mid-sized models, for the solver actually tested here.
It should not be read as "Seedbed produces zero spurious successes in
general" — it's evidence about *this* model on *this* n=24, and the
correction factor it implies for §3's accuracy numbers is, at this
sample size, indistinguishable from zero. It is a genuine data point
against Claude-specifically guessing from priors on these tasks, worth
re-running at larger n and against other models before treating as
general.

## 7. Cheap wins

- **CI**: `.github/workflows/tests.yml` — pytest on 3.10/3.11/3.12,
  removing the README's stated "no CI" weakness.
- **`build_adjacency` profiling**: confirmed O(slots²) — `sec / slots²` is
  flat (~0.096–0.105 ×10⁻⁶) across 100→800 synthetic slots, and cProfile
  at 800 slots shows 640,000 `connected()` calls dominating (0.128s of
  0.284s total). The synthetic profile doesn't reproduce the README's
  literal 220s-at-800-slots figure — that world has richer thread/meeting/
  audience structure than this synthetic single-actor probe, so each
  `connected()` call costs more — but it confirms the *shape* of the claim
  and localizes where the cost is. **The fix, not implemented here**:
  `connected()`'s edge conditions are almost all bucketable (same team,
  same thread, same meeting, reporting line) — indexing slots by those
  keys and only pairwise-checking within a bucket turns the all-pairs
  O(n²) scan into O(n) bucket lookups plus in-bucket edges, without
  changing `connected()`'s semantics.

## 8. What this study does and doesn't establish

**Does**: gives a real, re-runnable, cached measurement showing that on
the two bundled worlds' full difficulty range (≈7–35), a frontier model
solves this recovery task at or near 100% regardless of where in that
range a seed falls, with one small unexplained cluster that tracks
`world × tier`, not `difficulty`. Chain correctness tracked binary
correctness exactly in this sample. Spurious guessing on structurally-
guaranteed-unsolvable placements was not observed.

**Does not**: establish that `DEFAULT_WEIGHTS` correlates or fails to
correlate with recovery difficulty in general. The bundled worlds don't
get hard enough, at n=36/132 model calls, to tell. A meaningful next
attempt at TRACE-level validation needs: (a) worlds with materially longer
chains / more slots so difficulty can exceed ~35, (b) a panel of models
spanning a real capability range (this session had access to exactly one),
and (c) an order of magnitude more attempts to shrink the confidence
interval reported in §3. None of that happened here, and the README
should not cite this report as having calibrated `DEFAULT_WEIGHTS` — it
hasn't touched them, deliberately (see the task's own guard against
tuning and measuring in the same pass).

## Re-running

```
python -m validation.build_tasks     # regenerate tasks/prompts (deterministic)
# ... dispatch a solver-under-test against validation/data/prompts/*.txt,
#     writing validation/data/answers/{task_id}_attempt{n}.json ...
python -m validation.analyze         # correlation + per-term breakdown
python -m validation.spurious        # ablation / spurious-success rate
python -m validation.profile_adjacency
```
