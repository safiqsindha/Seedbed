"""Seeded assumed fill over claims, with backtracking.

Relationship to the prior art (docs/PRIOR_ART_REPORT.md): the source
material's items carry no inter-item prerequisite structure, so its Assumed
Fill can lean on "assume every unplaced item is already reachable" and never
needs to retract a placement. Claims here carry an explicit support DAG with
disjunctive alternatives, so that shortcut is not available: a placement
made early can genuinely corner a later claim.

An earlier revision of this module ignored that and placed greedily in
topological order with no retraction, while claiming it preserved the
no-retry guarantee. It did not -- measured against an exhaustive reference
filler it raised UnsolvableWorldError on ~35% of worlds that were in fact
fillable. This version does the honest thing and backtracks, so the search
is *complete*: it fails only when no legal placement exists (or when the
node budget is exhausted, which is reported as a distinct error rather than
being conflated with impossibility).

Two invariants are enforced at placement time rather than checked after:

1. A chain claim is placed only where **exactly one** of its support
   alternatives is live. That is what makes the result uncheatable, and it
   is a proof rather than a hope: dropping evidence only ever shrinks the
   known set, so a claim with a single live alternative has no fallback --
   removing any live-route claim necessarily breaks the target. Redundant
   support is the *only* way a proper subset could still solve, and it is
   rejected here at the source.
2. Candidates are tried in difficulty-maximizing order (greatest hop
   distance from the supporting evidence first), so backtracking gives up
   difficulty only as far as it must to stay solvable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence

from .access import AccessLogic, bfs_reachable, build_adjacency, shortest_path
from .difficulty import score
from .model import World
from .solver import solve

DEFAULT_NODE_BUDGET = 200_000
DEFAULT_SOLUTION_LIMIT = 32


class FillError(Exception):
    """Base class for every way a fill can fail to produce a placement."""


class UnsolvableWorldError(FillError):
    """No legal placement exists -- the search space was exhausted.

    This is a proof of impossibility, not a heuristic giving up. Raised for
    a claim with no legal slot, an unsatisfiable support cycle, or a world
    whose constraints simply cannot be met.
    """


class SearchBudgetExceeded(FillError):
    """The node budget ran out before the search could prove anything.

    Deliberately distinct from UnsolvableWorldError: this means "don't
    know", and conflating the two is how an engine ends up quietly claiming
    a solvable world is impossible.
    """


@dataclass
class RollLog:
    claim_id: str
    candidates: List[str]
    chosen: str
    reason: str
    alternative: List[str] = field(default_factory=list)


@dataclass
class FillResult:
    placement: Dict[str, str] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)
    rolls: List[RollLog] = field(default_factory=list)
    seed: int = 0
    tier: str = ""
    nodes_explored: int = 0
    backtracks: int = 0
    solutions_compared: int = 0
    difficulty_total: float = 0.0


def _topological_order(world: World, rng: random.Random) -> List[str]:
    """Prerequisites (across *all* alternatives) before dependents. Ties
    broken by the seeded RNG."""
    claim_ids = list(world.claims.keys())
    rng.shuffle(claim_ids)
    remaining = set(claim_ids)
    placed: set[str] = set()
    order: List[str] = []
    while remaining:
        ready = [
            cid
            for cid in claim_ids
            if cid in remaining and world.claims[cid].prerequisite_ids <= placed
        ]
        if not ready:
            raise UnsolvableWorldError(
                f"unsatisfiable claim support among {sorted(remaining)} "
                "(cycle, or a prerequisite that doesn't exist)"
            )
        for cid in ready:
            order.append(cid)
            placed.add(cid)
            remaining.discard(cid)
    return order


def assumed_fill(
    world: World,
    logic: AccessLogic,
    seed: int,
    node_budget: int = DEFAULT_NODE_BUDGET,
    solution_limit: int = DEFAULT_SOLUTION_LIMIT,
) -> FillResult:
    """Place every claim, then return the hardest placement found.

    Candidates are explored in difficulty-maximizing order, but the *first*
    complete solution is not necessarily the hardest: a per-claim greedy
    preference cannot see that choosing a shorter support alternative early
    caps the whole chain's length. So the search collects up to
    `solution_limit` complete placements and returns the best-scoring one.

    This is a bounded best-of-N, deliberately not a global optimum -- that
    would mean enumerating the entire space. `solution_limit` is the knob;
    the spoiler log records how many solutions were actually compared so the
    number is never mistaken for "the hardest placement that exists".
    """
    rng = random.Random(seed)
    adj = build_adjacency(world, logic)
    order = _topological_order(world, rng)
    chain_ids = world.chain_claim_ids()

    reach_cache: Dict[str, set] = {}

    def reachable_from(slot_id: str) -> set:
        cached = reach_cache.get(slot_id)
        if cached is None:
            cached = bfs_reachable(adj, slot_id)
            reach_cache[slot_id] = cached
        return cached

    # A stable, seed-derived tiebreak rank per (claim, slot). Computed up
    # front so candidate ordering never depends on the path the search took
    # to get here -- same seed, same ordering, byte-identical output.
    slot_ids = sorted(world.slots)
    tiebreak: Dict[str, Dict[str, int]] = {}
    for cid in order:
        shuffled = list(slot_ids)
        rng.shuffle(shuffled)
        tiebreak[cid] = {sid: i for i, sid in enumerate(shuffled)}

    # Slots this claim could ever occupy, ignoring support: pure authority.
    carriable: Dict[str, List[str]] = {
        cid: [s for s in slot_ids if logic.can_carry(world, world.slots[s], world.claims[cid])]
        for cid in order
    }

    # Fail fast and precisely on the obvious impossibility: a claim nobody
    # in the world is allowed to author. Left to the search this is still
    # correctly rejected, but only after exhausting every other claim's
    # options -- which burns the node budget and reports "undetermined"
    # instead of naming the claim that is actually at fault.
    for cid in order:
        if not carriable[cid]:
            claim = world.claims[cid]
            raise UnsolvableWorldError(
                f"claim {cid!r} has no legally carriable slot under access logic "
                f"{logic.name!r}: no slot's author satisfies min_role={claim.min_role!r}"
                + (
                    f" and eligible_authors={sorted(claim.eligible_authors)}"
                    if claim.eligible_authors
                    else ""
                )
            )

    placement: Dict[str, str] = {}
    rolls_by_claim: Dict[str, RollLog] = {}
    used_slots: set[str] = set()
    inferable: set[str] = set()
    stats = {"nodes": 0, "backtracks": 0}

    def live_alternatives(cid: str, slot_id: str) -> List[FrozenSet[str]]:
        """Support alternatives whose members are all *inferable* and all
        able to reach `slot_id`.

        Inferability, not mere placement, is the right test: a claim can be
        placed and still be stranded (no live alternative of its own), and a
        stranded claim must not prop up its dependents.
        """
        out = []
        for alt in world.claims[cid].support:
            if not alt <= inferable:
                continue
            if all(slot_id in reachable_from(placement[r]) for r in alt):
                out.append(alt)
        return out

    def candidates(cid: str) -> List[tuple]:
        """(stranded, -hop_score, tiebreak, slot_id, alternative) for every
        legal slot, live and hardest first."""
        is_target = world.claims[cid].target
        out = []
        for sid in carriable[cid]:
            if sid in used_slots:
                continue
            alts = live_alternatives(cid, sid)
            # The one hard invariant: never two live alternatives. That is
            # redundant support -- exactly the shortcut that would let a
            # proper subset still solve -- so it is refused at the source.
            if len(alts) >= 2:
                continue
            # Zero live alternatives is allowed: the claim lands stranded,
            # which is what turns a losing route into a near-miss decoy. A
            # target claim is the exception -- if it cannot be inferred, the
            # seed has no solution at all, so prune here rather than at the
            # leaf.
            if is_target and not alts:
                continue
            alt = alts[0] if alts else frozenset()
            hops = sum(
                (len(p) - 1) if (p := shortest_path(adj, placement[r], sid)) else 0 for r in alt
            )
            out.append((not alts, -hops, tiebreak[cid][sid], sid, alt))
        out.sort()
        return out

    solutions: List[tuple] = []

    def search(i: int) -> bool:
        """Returns True to stop the search (enough solutions collected)."""
        if stats["nodes"] >= node_budget:
            raise SearchBudgetExceeded(
                f"node budget {node_budget} exhausted after placing {i}/{len(order)} claims; "
                "this means UNDETERMINED, not impossible -- raise node_budget to search further"
            )
        if i == len(order):
            # Defence in depth: the invariants above should make this
            # unconditionally true, so a failure here is a real bug rather
            # than an expected dead end.
            if not solve(world, placement, logic).solved:
                return False
            solutions.append(
                (
                    score(world, placement, logic).total,
                    dict(placement),
                    {c: RollLog(**vars(r)) for c, r in rolls_by_claim.items()},
                )
            )
            return len(solutions) >= solution_limit

        cid = order[i]
        options = candidates(cid)
        if not options:
            return False

        for rank, (stranded, neg_hops, _tb, sid, alt) in enumerate(options):
            stats["nodes"] += 1
            placement[cid] = sid
            used_slots.add(sid)
            if not stranded:
                inferable.add(cid)
            rolls_by_claim[cid] = RollLog(
                claim_id=cid,
                candidates=sorted(o[3] for o in options),
                chosen=sid,
                reason=(
                    "stranded (no live support -- decoy)"
                    if stranded
                    else "forced (single legal candidate)"
                    if len(options) == 1
                    else f"max-difficulty (rank {rank + 1}/{len(options)}, {-neg_hops} hops)"
                ),
                alternative=sorted(alt),
            )
            if search(i + 1):
                return True
            del placement[cid]
            used_slots.discard(sid)
            inferable.discard(cid)
            rolls_by_claim.pop(cid, None)
            stats["backtracks"] += 1
        return False

    search(0)
    if not solutions:
        raise UnsolvableWorldError(
            f"no legal placement exists under access logic {logic.name!r} "
            f"(search exhausted after {stats['nodes']} nodes, {stats['backtracks']} backtracks)"
        )

    # Hardest first; ties fall back to discovery order, which is itself
    # seed-determined, so the choice stays reproducible.
    best_total, best_placement, best_rolls = max(solutions, key=lambda s: s[0])

    return FillResult(
        placement=best_placement,
        order=order,
        rolls=[best_rolls[cid] for cid in order],
        seed=seed,
        tier=logic.name,
        nodes_explored=stats["nodes"],
        backtracks=stats["backtracks"],
        solutions_compared=len(solutions),
        difficulty_total=best_total,
    )
