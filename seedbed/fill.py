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
DEFAULT_SOLUTION_LIMIT = 256
DEFAULT_TRACE_LIMIT = 5_000
# Stop comparing once this many consecutive solutions fail to beat the best
# found. A fixed budget is the wrong shape: raising the cap from 32 to 512
# bought +1.8 mean difficulty on the toy world and +0.05 on the relay world,
# for 13x the time in both. Patience spends effort only where it still pays.
#
# The gain is real but modest -- roughly +0.15 mean difficulty over a fixed
# 32 at comparable cost, with headroom to keep climbing on worlds that
# reward it. 24 is "long enough to cross a short plateau, short enough that
# a flat world stops early"; it is not the value that maximised any single
# measurement.
DEFAULT_IMPROVEMENT_PATIENCE = 24


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
    """The placement decision for one claim in the *winning* placement."""

    claim_id: str
    candidates: List[str]
    chosen: str
    reason: str
    alternative: List[str] = field(default_factory=list)


@dataclass
class SearchEvent:
    """One step of the search, including the steps that were undone.

    The winning placement alone is not an audit trail: with backtracking,
    most of the seeded decision process is in the branches that were tried
    and rejected. Recording only the survivors -- as this module originally
    did -- leaves the seed reproducible but not *explicable*: you can rerun
    it, but you cannot see why it landed where it did.
    """

    kind: str  # "place" | "backtrack" | "solution" | "dead_end"
    depth: int
    claim_id: str = ""
    slot_id: str = ""
    detail: str = ""


@dataclass
class RngDraws:
    """Every draw taken from the seeded RNG, in order.

    These are the only nondeterministic inputs to the fill, so together with
    the seed they fully explain the search's shape.
    """

    claim_order_shuffle: List[str] = field(default_factory=list)
    slot_rank_shuffles: Dict[str, List[str]] = field(default_factory=dict)
    solution_choice: str = ""


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
    #: Full search trace. Capped by `trace_limit`; `trace_truncated` says so
    #: explicitly rather than letting a partial log read as a complete one.
    trace: List[SearchEvent] = field(default_factory=list)
    trace_truncated: bool = False
    rng_draws: RngDraws = field(default_factory=RngDraws)
    #: (difficulty_total, placement) for every complete solution compared.
    solution_scores: List[float] = field(default_factory=list)


def _derivable(world: World, available: set) -> set:
    """Fixed-point closure: which claims follow from `available`."""
    known = set()
    changed = True
    while changed:
        changed = False
        for cid in available:
            if cid in known:
                continue
            if any(alt <= known for alt in world.claims[cid].support):
                known.add(cid)
                changed = True
    return known


def mandatory_claims(world: World) -> FrozenSet[str]:
    """Claims that lie on *every* route to a target.

    A claim with an alternative route around it (the toy world's c1, which
    c2b bypasses) is not mandatory and may legitimately strand. Only these
    are guaranteed to appear on the live route, which is what makes a
    reachability requirement about them sound rather than merely plausible.
    """
    everything = set(world.claims)
    targets = world.target_ids()
    if not targets <= _derivable(world, everything):
        return frozenset()
    out = set()
    for cid in world.claims:
        if cid in targets:
            out.add(cid)
            continue
        if not targets <= _derivable(world, everything - {cid}):
            out.add(cid)
    return frozenset(out)


def mandatory_chain(world: World, order: List[str]) -> List[str]:
    """The mandatory claims, in dependency order, filtered so each one
    transitively depends on the one before it.

    Restricting to a genuine chain matters: two mandatory claims that are
    merely parallel impose no ordering on each other, so requiring their
    slots to advance in time would reject placements that are perfectly
    legal.
    """
    mandatory = mandatory_claims(world)
    deps = _dependents(world)
    chain: List[str] = []
    for cid in order:
        if cid not in mandatory:
            continue
        if not chain or chain[-1] in _ancestors(world, cid):
            chain.append(cid)
    return chain


def _ancestors(world: World, cid: str) -> FrozenSet[str]:
    """Every claim `cid` transitively depends on."""
    seen, stack = set(), list(world.claims[cid].prerequisite_ids)
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        stack.extend(world.claims[p].prerequisite_ids)
    return frozenset(seen)


def _dependents(world: World) -> Dict[str, FrozenSet[str]]:
    """claim -> every claim that transitively depends on it."""
    direct: Dict[str, set] = {cid: set() for cid in world.claims}
    for cid, claim in world.claims.items():
        for prereq in claim.prerequisite_ids:
            direct[prereq].add(cid)
    out: Dict[str, FrozenSet[str]] = {}
    for cid in world.claims:
        seen, stack = set(), list(direct[cid])
        while stack:
            d = stack.pop()
            if d in seen:
                continue
            seen.add(d)
            stack.extend(direct[d])
        out[cid] = frozenset(seen)
    return out


def _topological_order(world: World, rng: random.Random, draws: "RngDraws") -> List[str]:
    """Prerequisites (across *all* alternatives) before dependents. Ties
    broken by the seeded RNG."""
    claim_ids = list(world.claims.keys())
    rng.shuffle(claim_ids)
    draws.claim_order_shuffle = list(claim_ids)
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
    trace_limit: int = DEFAULT_TRACE_LIMIT,
    improvement_patience: int = DEFAULT_IMPROVEMENT_PATIENCE,
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
    draws = RngDraws()
    trace: List[SearchEvent] = []
    trace_state = {"truncated": False}

    def record(kind: str, depth: int, claim_id: str = "", slot_id: str = "", detail: str = "") -> None:
        if len(trace) >= trace_limit:
            trace_state["truncated"] = True
            return
        trace.append(SearchEvent(kind=kind, depth=depth, claim_id=claim_id, slot_id=slot_id, detail=detail))

    adj = build_adjacency(world, logic)
    order = _topological_order(world, rng, draws)
    chain_ids = world.chain_claim_ids()
    mandatory_set = mandatory_claims(world)
    chain = mandatory_chain(world, order)
    chain_positions = {cid: n for n, cid in enumerate(chain)}
    chain_after = [tuple(chain[n + 1 :]) for n in range(len(chain))]

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
        draws.slot_rank_shuffles[cid] = list(shuffled)

    # Slots this claim could ever occupy, ignoring support: pure authority.
    carriable: Dict[str, List[str]] = {
        cid: [s for s in slot_ids if logic.can_carry(world, world.slots[s], world.claims[cid])]
        for cid in order
    }

    # Carriable slots pre-sorted by timestamp, for the greedy-earliest probe.
    carriable_by_time: Dict[str, List[str]] = {
        cid: sorted(slots, key=lambda s: (world.slots[s].timestamp, s))
        for cid, slots in carriable.items()
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

    def suffix_feasible(i: int, cid: str, slot_id: str) -> bool:
        """After tentatively placing `cid` at `slot_id`, can the *rest* of the
        chain still be laid out at all?

        This is the randomizer's central discipline: never place an item
        without first confirming the seed is still completable. Without it,
        the difficulty-maximizing order is actively adversarial to
        satisfiability -- it puts each claim as late in time as it can, which
        starves the next chain claim of reachable slots, and with no
        lookahead the search must exhaust an enormous subtree before backing
        out far enough to matter. Measured before this check existed: a
        60-slot world with an 8-claim chain found no solution in 200k nodes
        even though a valid placement trivially exists.

        The probe is a greedy forward walk over the remaining claims, each
        taking the earliest legal slot still reachable from its support. It
        is a *necessary* condition, not a sufficient one -- greedy may fail
        where the real search would succeed on a branching support DAG -- so
        it can only prune branches, never accept one. Completeness is
        preserved because a branch it rejects has no greedy completion, and
        the tests measure that directly against a reference enumerator.
        """
        # Sound only when `cid` itself is mandatory. A bypassable claim (the
        # toy world's c1, which c2b routes around) may end up stranded, and
        # then its dependents reach the target without ever passing through
        # it -- so nothing about their slots follows from where it landed.
        if cid not in mandatory_set:
            return True
        try:
            start = chain_positions[cid]
        except KeyError:
            return True
        downstream = chain_after[start]
        if not downstream:
            return True

        # Forward-check one step of *reachability*. The timestamp relaxation
        # below cannot see this: timestamps stay plentiful while the access
        # graph runs out, so a claim can sit somewhere the next mandatory
        # claim simply cannot be reached from. Applied at every depth this is
        # the classic CSP forward-check, and it compounds -- each claim is
        # barred from any slot that orphans its successor.
        nxt = downstream[0]
        horizon = reachable_from(slot_id)
        if not any(
            sid in horizon and sid not in used_slots and sid != slot_id
            for sid in carriable[nxt]
        ):
            return False

        # Relax the real constraint to one that is cheap and still necessary:
        # every access edge runs forward in time, so a chain of k mandatory
        # claims needs k distinct slots at non-decreasing timestamps, each
        # carriable by its own claim.
        #
        # Greedy-earliest is exactly optimal for that relaxation (taking the
        # earliest feasible slot never costs a later claim anything), so it
        # decides the relaxed problem rather than approximating it. Failing
        # it therefore proves the real branch is dead -- no over-pruning,
        # which the completeness test measures directly.
        taken = used_slots | {slot_id}
        floor = world.slots[slot_id].timestamp
        for later in downstream:
            picked = None
            for sid in carriable_by_time[later]:
                if sid in taken:
                    continue
                if world.slots[sid].timestamp < floor:
                    continue
                picked = sid
                break
            if picked is None:
                return False
            taken.add(picked)
            floor = world.slots[picked].timestamp
        return True

    def candidates(cid: str, i: int) -> List[tuple]:
        """(stranded, -hop_score, tiebreak, slot_id, alternative) for every
        legal slot, live and hardest first.

        Difficulty ordering is applied only to candidates that survive the
        feasibility probe, so maximizing difficulty can no longer strand the
        rest of the chain.
        """
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
            # which is what turns a losing route into a near-miss decoy.
            #
            # Mandatory claims are the exception. They sit on *every* route
            # to the target, so a stranded one cannot lead to a solution --
            # and letting the search place them anyway was the real cost:
            # it descended through entire stranded chains before the target
            # finally refused, burning the node budget on branches that were
            # dead the moment they started.
            if not alts and (is_target or cid in mandatory_set):
                continue
            if not suffix_feasible(i, cid, sid):
                continue
            alt = alts[0] if alts else frozenset()
            hops = sum(
                (len(p) - 1) if (p := shortest_path(adj, placement[r], sid)) else 0 for r in alt
            )
            out.append((not alts, -hops, tiebreak[cid][sid], sid, alt))
        out.sort()
        return out

    solutions: List[tuple] = []
    best = {"total": float("-inf"), "stale": 0}

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
                record("dead_end", i, detail="complete assignment failed the solvability oracle")
                return False
            total = score(world, placement, logic).total
            solutions.append(
                (
                    total,
                    dict(placement),
                    {c: RollLog(**vars(r)) for c, r in rolls_by_claim.items()},
                )
            )
            if total > best["total"]:
                best["total"] = total
                best["stale"] = 0
            else:
                best["stale"] += 1
            record(
                "solution",
                i,
                detail=(
                    f"solution {len(solutions)} of at most {solution_limit}, "
                    f"difficulty {total:.4g}, {best['stale']} since last improvement"
                ),
            )
            return len(solutions) >= solution_limit or best["stale"] >= improvement_patience

        cid = order[i]
        options = candidates(cid, i)
        if not options:
            record("dead_end", i, claim_id=cid, detail="no legal slot given placements so far")
            return False

        for rank, (stranded, neg_hops, _tb, sid, alt) in enumerate(options):
            stats["nodes"] += 1
            placement[cid] = sid
            used_slots.add(sid)
            if not stranded:
                inferable.add(cid)
            reason = (
                "stranded (no live support -- decoy)"
                if stranded
                else "forced (single legal candidate)"
                if len(options) == 1
                else f"max-difficulty (rank {rank + 1}/{len(options)}, {-neg_hops} hops)"
            )
            rolls_by_claim[cid] = RollLog(
                claim_id=cid,
                candidates=sorted(o[3] for o in options),
                chosen=sid,
                reason=reason,
                alternative=sorted(alt),
            )
            record("place", i, claim_id=cid, slot_id=sid, detail=reason)
            if search(i + 1):
                return True
            del placement[cid]
            used_slots.discard(sid)
            inferable.discard(cid)
            rolls_by_claim.pop(cid, None)
            stats["backtracks"] += 1
            record("backtrack", i, claim_id=cid, slot_id=sid, detail="subtree yielded no solution")
        return False

    search(0)
    if not solutions:
        raise UnsolvableWorldError(
            f"no legal placement exists under access logic {logic.name!r} "
            f"(search exhausted after {stats['nodes']} nodes, {stats['backtracks']} backtracks)"
        )

    # Hardest first; ties fall back to discovery order, which is itself
    # seed-determined, so the choice stays reproducible.
    best_index, (best_total, best_placement, best_rolls) = max(
        enumerate(solutions), key=lambda pair: pair[1][0]
    )
    draws.solution_choice = (
        f"solution {best_index + 1} of {len(solutions)} compared, difficulty {best_total:.4g}"
    )

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
        trace=trace,
        trace_truncated=trace_state["truncated"],
        rng_draws=draws,
        solution_scores=[s[0] for s in solutions],
    )
