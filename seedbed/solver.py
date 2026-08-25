"""Reference solver: the solvability oracle.

Fixed-point recovery of which claims are inferable from a given placement,
mirroring GetReachableLocationsAssumed's fixed-point loop -- generalized to
also gate on claim-level prerequisites (`Claim.requires`) and the
`can_carry` authority check. This is the single source of truth for both
"is this seed solvable" (component 4) and "is this seed cheatable"
(component 5, which just calls this again on proper subsets).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set

from .access import AccessLogic, bfs_reachable, build_adjacency
from .model import World


@dataclass
class SolveResult:
    known: Set[str]
    solved: bool
    target_ids: Set[str]


def solve(world: World, placement: Dict[str, Optional[str]], logic: AccessLogic) -> SolveResult:
    """`placement` maps claim_id -> slot_id, or claim_id -> None for
    evidence excluded from this run (used to test proper subsets)."""
    adj = build_adjacency(world, logic)
    reach_cache: Dict[str, Set[str]] = {}

    def reachable_from(slot_id: str) -> Set[str]:
        cached = reach_cache.get(slot_id)
        if cached is None:
            cached = bfs_reachable(adj, slot_id)
            reach_cache[slot_id] = cached
        return cached

    known: Set[str] = set()
    changed = True
    while changed:
        changed = False
        for cid, slot_id in placement.items():
            if cid in known or slot_id is None:
                continue
            claim = world.claims[cid]
            if not claim.requires <= known:
                continue
            slot = world.slots[slot_id]
            if not logic.can_carry(world, slot, claim):
                continue
            if not all(slot_id in reachable_from(placement[r]) for r in claim.requires):
                continue
            known.add(cid)
            changed = True

    target_ids = {c.id for c in world.claims.values() if c.target}
    return SolveResult(known=known, solved=target_ids <= known, target_ids=target_ids)
