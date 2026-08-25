"""Seeded assumed fill over claims.

Adaptation note (see docs/PRIOR_ART_REPORT.md section 5.2): the source
material's items have no inter-item prerequisite structure, so Assumed Fill
there has to *assume* not-yet-placed items are already available in order to
avoid a chicken-and-egg problem when checking reachability. Claims here
carry an explicit prerequisite DAG (`Claim.requires`), and the access
graph's connectivity is purely structural -- it never depends on which slot
holds which claim. That collapses the "assume everything else is placed"
trick to something simpler and strictly equivalent: process claims in a
seeded topological order (prerequisites before dependents) and validate
each placement against *real* prerequisite placements, which by
construction are already final. The core Assumed Fill property is
preserved -- every placement is checked against the state that will
actually hold, so no post-hoc validity pass or retry is ever needed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List

from .access import AccessLogic, bfs_reachable, build_adjacency, shortest_path
from .model import World


class UnsolvableWorldError(Exception):
    """Raised the moment a claim has no legal slot under the given access
    logic. Fails loudly and immediately -- never silently drops a claim or
    degrades the solvability guarantee."""


@dataclass
class RollLog:
    claim_id: str
    candidates: List[str]
    chosen: str
    reason: str


@dataclass
class FillResult:
    placement: Dict[str, str] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)
    rolls: List[RollLog] = field(default_factory=list)
    seed: int = 0
    tier: str = ""


def _topological_order(world: World, rng: random.Random) -> List[str]:
    claim_ids = list(world.claims.keys())
    rng.shuffle(claim_ids)  # seed-dependent tie-break among claims at the same rank
    remaining = set(claim_ids)
    placed: set[str] = set()
    order: List[str] = []
    while remaining:
        ready = [cid for cid in claim_ids if cid in remaining and world.claims[cid].requires <= placed]
        if not ready:
            raise UnsolvableWorldError(
                f"unsatisfiable claim dependency among {sorted(remaining)} "
                "(cycle, or a prerequisite that doesn't exist)"
            )
        for cid in ready:
            order.append(cid)
            placed.add(cid)
            remaining.discard(cid)
    return order


def assumed_fill(world: World, logic: AccessLogic, seed: int) -> FillResult:
    rng = random.Random(seed)
    adj = build_adjacency(world, logic)
    order = _topological_order(world, rng)

    placement: Dict[str, str] = {}
    rolls: List[RollLog] = []
    used_slots: set[str] = set()

    has_dependents: set[str] = set()
    for claim in world.claims.values():
        has_dependents.update(claim.requires)

    for cid in order:
        claim = world.claims[cid]
        prereq_slot_ids = [placement[r] for r in claim.requires]
        prereq_reachable = [bfs_reachable(adj, ps) for ps in prereq_slot_ids]

        legal: List[str] = []
        for slot in world.slots.values():
            if slot.id in used_slots:
                continue
            if not logic.can_carry(world, slot, claim):
                continue
            if not all(slot.id in reach for reach in prereq_reachable):
                continue
            legal.append(slot.id)

        if not legal:
            raise UnsolvableWorldError(
                f"claim {cid!r} has no legal slot under access logic {logic.name!r} "
                f"(prerequisite slots: {prereq_slot_ids})"
            )

        if len(legal) == 1:
            chosen = legal[0]
            reason = "forced (single legal candidate)"
        else:
            def hop_score(slot_id: str) -> int:
                if not prereq_slot_ids:
                    return 0
                total = 0
                for ps in prereq_slot_ids:
                    path = shortest_path(adj, ps, slot_id)
                    total += (len(path) - 1) if path else 0
                return total

            # Primary: maximize hop distance from prerequisites (difficulty).
            # Final ties broken by the seeded RNG -- except for a claim that
            # something else still depends on, where pure random choice can
            # grab a late-timestamp slot and strand that dependent (which
            # needs a *later* slot from the same shrinking author-eligible
            # pool) -- the time-ordering analogue of a randomizer stranding
            # progression behind a filled dead end. Such claims are narrowed
            # to the earliest legal timestamp among the hardest tier first,
            # so they never eat a dependent's only remaining room.
            scored = {s: hop_score(s) for s in legal}
            best = max(scored.values())
            hardest = [s for s, v in scored.items() if v == best]
            if cid in has_dependents:
                earliest_ts = min(world.slots[s].timestamp for s in hardest)
                hardest = [s for s in hardest if world.slots[s].timestamp == earliest_ts]
            chosen = rng.choice(sorted(hardest))
            reason = "max-difficulty" if len(hardest) < len(legal) else "max-difficulty (tie, seeded pick)"

        placement[cid] = chosen
        used_slots.add(chosen)
        rolls.append(RollLog(claim_id=cid, candidates=sorted(legal), chosen=chosen, reason=reason))

    return FillResult(placement=placement, order=order, rolls=rolls, seed=seed, tier=logic.name)
