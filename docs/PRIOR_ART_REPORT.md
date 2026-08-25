# Prior-Art Report: Fill Algorithm Selection for Seedbed

Status: **implemented, with corrections** — originally written as deliverable 1
of 6, before any engine code existed. The recommendation below (Assumed Fill)
survived implementation; two claims about *how faithfully it was ported* did
not. See [§6 Corrections after implementation](#6-corrections-after-implementation)
for what was wrong, how it was measured, and what changed. That section is the
authority wherever it contradicts the original text above it.

## 1. What was read

### 1.1 `cjohnson57/RandomizerAlgorithms` (C#, IEEE-published study)

A comparative study implementing three fill strategies plus the reachability
machinery they all depend on.

- **`Search.cs`**
  - `GetReachableLocations(world, ownedItems)` — classic BFS over the world
    graph. Queue of regions starting at `StartRegion`; for each region, exits
    are followed if `parser.RequirementsMet()` passes against the *static*
    `ownedItems` set; locations in reachable regions are collected. Visited
    set prevents cycles. This is a pure "what can I see with what I have
    right now" query — no fixed-point iteration.
  - `GetReachableLocationsAssumed(world, ownedItems)` — wraps the above in a
    fixed-point loop: run `GetReachableLocations`, extract any
    "major"/progression items found in that reachable set, union them into
    `ownedItems`, and repeat until a pass discovers no new major item. This
    is the key primitive: it answers "what's reachable if I'm also allowed
    to credit myself with everything reachable *from* what's reachable"
    — i.e., the transitive closure of access.
  - `PathsToRegion(world, dest)` — recursive DFS enumerating **all**
    non-self-intersecting paths from the start region to `dest`, backtracking
    per branch with a copied visited-list. Used for path analysis, not for
    filling.

- **`Fill.cs`**
  - **Random Fill**: shuffle items and locations, zip them together. No
    accessibility awareness during placement — validity (is the seed
    beatable at all) has to be checked *after the fact* with the search
    functions above.
  - **Forward Fill**: maintain a live reachable set; repeatedly pick a random
    unplaced item, drop it into a random *currently reachable* location, then
    recompute reachability (the new item may open more locations) and
    continue. Progression items are prioritized over filler. Reachability
    only ever grows during the fill.
  - **Assumed Fill**: run in reverse. Start by assuming the player has
    *every* item. Repeatedly pick a random item out of the assumed-owned set,
    recompute reachability *without* it (this can only shrink or hold the
    reachable set), and place the removed item into a location that is
    reachable in that shrunken state. Continue until all items are placed.
    Because every placement is validated against a reachable-without-this-item
    state, the final result is reachable-with-it by construction — the fill
    is beatable with no post-hoc check needed.

  The paper's conclusion (and the reason `alttp_vt_randomizer` — a shipped,
  battle-tested randomizer — uses this family) is that **Assumed Fill is the
  only one of the three that guarantees solvability as an invariant of the
  placement process itself**, rather than as a property that has to be
  checked afterward and potentially retried. Random Fill needs full
  re-generation on failure; Forward Fill is solvable but its "first
  reachable location" bias front-loads options for early placements and
  starves late placements, which for us would mean early claims get weak,
  arbitrary slot choices while later claims get forced into whatever is left.

### 1.2 `sporchia/alttp_vt_randomizer`, `app/Filler/RandomAssumed.php`

Production implementation of assumed fill, confirms and refines the above.
Its `fillItemsInLocations()`:

1. Pull the next item to place off the pool (progression items processed
   before junk, same as Forward Fill's ordering bias but on the *placement*
   side rather than the *location* side).
2. Compute `assumed_items` = everything already placed + everything still
   unplaced *except* the item currently being placed (the "assume I have
   everything else" step — this is the forward-friendly restatement of the
   C# paper's reverse-removal loop; both converge on the same invariant).
3. Iteratively expand reachable locations from `assumed_items` until fixed
   point (mirrors `GetReachableLocationsAssumed`).
4. Filter to locations where `canFill()` holds — the per-location
   access/type predicate ("hookshot behind a hookshot door" lives here: a
   location can refuse an item class regardless of reachability).
5. Place the item in the first (or, for a class of fungible items like
   compasses, a random) valid location from that filtered, narrowing set.

Each subsequent placement operates over a strictly smaller remaining pool, so
the set of valid locations for later items is more constrained than for
earlier ones — this is the "progressively narrowing" behavior named in the
task. It is the same invariant as the C# reverse formulation, just walked in
the opposite direction (assume-the-rest instead of remove-and-shrink); I treat
them as one algorithm family below.

## 2. Recommendation

**Use Assumed Fill as Seedbed's placement algorithm**, in the forward
"assume everything else is already placed" formulation from
`RandomAssumed.php` (it composes more naturally with a seeded RNG and with
claim-dependency ordering than the reverse-removal formulation, and is the
one with a production track record). Random Fill is disqualified because it
gives up the solvability guarantee entirely (requirement 2 is not optional
for us — it's an assert, not a retry loop). Forward Fill is workable but its
placement-order bias (early item → best pick of open locations) fights
requirement 4 (maximize difficulty): we want *every* placement, early and
late, to be the most-constrained legal choice available at that point in the
seeded order, not whichever location the RNG found first while options were
still wide open.

## 3. Terminology mapping

| Randomizer concept | Seedbed concept |
|---|---|
| World graph (regions + exits) | Access graph over slots — nodes are slots, edges are access relations (same thread, same team, reporting line, meeting attendance, time ordering) |
| Location | Slot (a not-yet-written artifact: author, timestamp, channel, audience) |
| Item | Claim (atomic fact) |
| Item importance tier (major/minor/junk) | Claim role: **chain claims** (part of the target inference path — analogous to progression items) vs. **distractor claims** (junk items — placed to add branching/noise without being load-bearing) |
| "Hookshot behind a hookshot door" (item-gated location) | Access predicate on a slot: a slot may require that certain *other* claims already be placed/knowable before it can legally carry a *new* claim — e.g., you can't write a memo referencing a decision you weren't in the room for |
| `RequirementsMet()` / `canFill()` | The pluggable access-logic predicate (component 2): `can_carry(slot, claim, world_state) -> bool` |
| Owned items | Claims an actor could plausibly know by a given slot's timestamp — accumulated along the access graph, not global knowledge |
| `GetReachableLocations` (BFS, static inventory) | One query of the reference solver: "given exactly the claims placed so far, which further claims become inferable" |
| `GetReachableLocationsAssumed` (fixed-point BFS) | The **solvability oracle** (component 4): iterate "what's inferable" → "what that unlocks" → ... until no new claim is inferred; SOLVABLE iff the target claim set is fully covered at fixed point, using *only* the actually-placed evidence (no oracle peeking at unplaced slots) |
| `PathsToRegion` (all simple paths root→target) | The recovery-path enumeration used both to report the spoiler-log recovery path and as the base data for difficulty scoring (hop count, branching) |
| Re-run `GetReachableLocationsAssumed` with one item removed, to check the seed is still beatable without it | The **cheatability check** (component 5): re-run the solvability oracle against every proper subset of placed evidence (or a documented sample of subsets — see below); requirement 3 holds iff *every* one of those runs fails. This reuses the exact same fixed-point machinery as the oracle itself — it's the identical function called with a smaller evidence set, not a separate algorithm |

### "Reachability" → "had access by this date"

A claim is **inferable** at a given point in the fill/solve process if there
exists at least one slot already carrying it (or a claim set covering it)
such that:

1. **Time ordering**: the slot's timestamp is ≤ the timestamp of the slot
   we're trying to unlock (an actor can't cite something that doesn't exist
   yet).
2. **Graph reachability**: there is a path in the access graph from that
   slot to the actor/slot in question, where each edge represents a
   concrete access relation (shared thread, shared meeting, reporting line,
   forwarded channel, etc.) — this is a direct swap-in for the world graph's
   exits.
3. **Predicate satisfaction**: `can_carry()` holds — the pluggable
   audience/authority check (an intern doesn't get exec-only claims even if
   graph-reachable; a report doesn't get claims from a meeting it wasn't
   copied on).

This is exactly `GetReachableLocations`'s three-part check (region adjacency
+ `RequirementsMet` + item ownership), with "item ownership" split into
"claim already placed" (static, like the base game) and, during the
fixed-point solver/oracle pass, "claim already inferred this round" (dynamic,
like assumed items). The fixed-point loop is what lets a claim placed in an
early slot enable inference of a second claim placed in a later slot, which
in turn enables inference of the target — i.e., genuine multi-hop chains,
not single-hop lookups.

## 4. Cheatability sampling strategy (component 5, flagged now since it
determines the oracle's interface)

Exhaustive subset checking is `2^n - 2` proper-subset runs of the oracle for
`n` placed evidence items; for the ~40-slot toy world this is tractable
exhaustively. For larger worlds this doesn't scale, so the plan is:

- **Always exhaustive** for single-item removal (`n` runs: "is any one piece
  of evidence individually load-bearing") — this is the direct analogue of
  the randomizer's "remove one item, recheck beatability" pattern and is
  cheap.
- **Sampled** for the general disconnected-reasoning check per
  arXiv:2510.11956: rather than random subsets (which mostly land on
  "obviously still unsolvable" and waste budget), bias sampling toward
  subsets that preserve every *out-of-scope* hop while dropping one
  *in-scope* hop at a time, and vice versa — this is what the paper found
  actually moves cheatability, not uniform subset sampling. Sample size and
  exact strategy documented in the spoiler log's methodology section so
  results are reproducible from the seed, matching requirement 5.
- Any world where sampling is used instead of exhaustive checking logs that
  fact explicitly — no silent "we probably checked enough."

## 5. Open questions before proceeding to component 2

1. **Implementation language.** Task doesn't specify one. Recommend Python
   (dataclasses for Slot/Claim, `random.Random(seed)` for the seeded RNG,
   trivial to write a CLI with `argparse`, no build step). Will proceed with
   Python unless told otherwise.
2. **Claim dependency structure.** "Hookshot behind a hookshot door" implies
   claims can have their own prerequisite edges (claim B only makes sense /
   is only inferable once claim A is known) independent of slot access. Plan
   is to model this as a small DAG over claims, authored by hand for the toy
   world, consumed by both the fill and the solver.
3. **Difficulty weights default values** (component 6) will be placeholders
   tuned against the toy world's three logic tiers, not claimed to be
   calibrated against any real benchmark.

Report ends here per the requested deliverable order — holding before writing
any engine code pending review of the above.

---

## 6. Corrections after implementation

The three open questions in §5 resolved as: Python; a claim DAG (but
**disjunctive**, see below); placeholder weights. More importantly, two
claims made during the first implementation turned out to be false when
measured. Both are recorded here rather than quietly fixed, because both
were asserted confidently in a commit message and a merged PR description.

### 6.1 The port did not preserve assumed fill's no-retry guarantee

**Claimed:** that processing claims in topological order and validating
against *real* (not assumed) prerequisite placements was "strictly
equivalent" to the source material's assume-everything-else trick, and so
inherited its property that no placement ever needs retracting.

**Reality:** it is not equivalent. The prior art's items carry no
inter-item prerequisite structure, which is exactly what lets it assume
unplaced items are available and never backtrack. Claims *do* carry that
structure, so an early placement can genuinely corner a later claim. The
first implementation had no retraction, so when it cornered itself it
raised `UnsolvableWorldError`.

**Measured:** against an exhaustive reference filler over worlds where a
legal placement provably exists, the original greedy fill wrongly reported
impossibility on **79 of 227 worlds — a 34.8% false-negative rate**. It
passed its own test suite because the toy world had been tuned until it
did.

**Fixed:** `fill.py` now performs real backtracking search. Re-measured
against an independent reference enumerator (sharing no pruning logic —
only the public `solve()` / `check_cheatability()` contract): **0 false
negatives across 80 fillable worlds, 0 false positives across 40 provably
impossible ones.** Locked in by `test_fill.py::test_fill_is_complete_no_false_negatives`.

A separate `SearchBudgetExceeded` now distinguishes "don't know" from
"proven impossible". Conflating those is how the original bug stayed
invisible.

### 6.2 The cheatability check was vacuous

**Claimed:** that re-running the solver over proper subsets verified the
chain could not be short-circuited.

**Reality:** with purely conjunctive `requires`, the model could not
*express* a shortcut. A target had exactly one route by construction, so
dropping any chain claim always broke it, and `uncheatable=True` was a
theorem about the data structure rather than a measurement of the seed.
Fed **2000 deliberately absurd random placements, the check never once
returned False.** The arXiv:2510.11956 concern it was meant to address —
benchmarks solved without genuine multi-hop inference — was entirely
untouched.

**Fixed:** two changes.

- `Claim.support` is now a tuple of **alternative sufficient sets** (see
  `model.Support`, `model.either`): a claim can be established two
  independent ways, which is what a shortcut *is*. The toy world exercises
  this — `c3` is supported by either `c2` or `c2b`.
- The subsets varied are the solver's **live route** (the claims actually
  credited for reaching the target), not every claim that could
  theoretically contribute. Distractors are *supposed* to be droppable;
  requiring otherwise would fail every world containing a decoy.

**Re-measured:** the check now flags **31.8% of random solvable placements
(5,867 of 18,461) as cheatable**, correctly naming the redundantly
supported claim. Non-vacuity is locked in by
`test_cheat.py::test_cheatability_check_is_not_vacuous`.

The fill prevents the condition at the source rather than rejecting it
after the fact: a claim is never placed where two of its alternatives are
live. That is a proof, not a heuristic — dropping evidence only shrinks the
known set, so a claim with a single live alternative has no fallback.

### 6.3 Difficulty tiers: what is and is not guaranteed

The original suite asserted monotonically increasing difficulty across
tiers. That assertion had been weakened to `>=` and the toy world adjusted
until it passed — over 200 seeds, `standard` and `hard` were in fact
**tied 200/200 times**.

Two things were wrong. `distractor_density` counted *empty filler slots*
between evidence, which evaluated to `1.0` on literally every seed — a
constant contributing nothing. And difficulty was being compared across
*independently generated* placements, which conflates two variables, since
different tiers pick different support routes entirely.

Now:

- `distractor_density` counts decoy-carrying neighbours per load-bearing
  carrier, judged under a **fixed permissive lens** (a reader does not know
  the access rules — inferring them is the task). It varies, and it no
  longer falls as strictness rises.
- Monotonicity is asserted where it is meaningful: one **fixed** placement
  scored under each tier. **0 violations across 177 placements, 107 of them
  strictly harder easy→hard.** `hop_count` is monotone by construction
  (removing edges can only lengthen or sever a shortest path) and is tested
  separately.

Across independently generated placements the total is *not* guaranteed
monotone, and this is not claimed. That comparison is not apples-to-apples.

### 6.4 Difficulty maximization is bounded, not global

Requirement 4 asks for maximized inference difficulty. The fill explores
candidates in difficulty-maximizing order and returns the best of the first
`solution_limit` (default 32) complete placements. This is a bounded
best-of-N, **not** a global optimum — a per-claim greedy preference cannot
see that a short support alternative chosen early caps the whole chain.
`FillResult.solutions_compared` records how many were actually compared, so
the number is never mistaken for the hardest placement that exists.
