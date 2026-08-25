"""Reference solver: the solvability oracle.

Fixed-point recovery of which claims are inferable from a given placement,
mirroring GetReachableLocationsAssumed's fixed-point loop -- generalized to
claim-level support (disjunctive alternatives) and the `can_carry`
authority check. This is the single source of truth for both "is this seed
solvable" (component 4) and "is this seed cheatable" (component 5, which
just calls this again on subsets).

Beyond a yes/no it reports the **live route**: the claims actually used to
reach the target. That distinction matters -- the cheatability check varies
the live route, not every claim that could theoretically have contributed,
because a distractor being droppable is what makes it a distractor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set

from .access import AccessLogic, bfs_reachable, build_adjacency
from .model import World


@dataclass
class SolveResult:
    known: Set[str]
    solved: bool
    target_ids: Set[str]
    #: claim id -> the alternatives that were satisfied for it. More than
    #: one means redundant support: a potential shortcut.
    satisfied_alternatives: Dict[str, List[FrozenSet[str]]] = field(default_factory=dict)
    #: claim id -> the alternative actually credited (first satisfied).
    used_alternative: Dict[str, FrozenSet[str]] = field(default_factory=dict)

    @property
    def live_route(self) -> FrozenSet[str]:
        """Claims actually load-bearing for the target, traced back through
        the credited alternatives. Empty when unsolved."""
        if not self.solved:
            return frozenset()
        route: Set[str] = set()
        stack = list(self.target_ids)
        while stack:
            cid = stack.pop()
            if cid in route:
                continue
            route.add(cid)
            stack.extend(self.used_alternative.get(cid, frozenset()))
        return frozenset(route)

    @property
    def redundantly_supported(self) -> FrozenSet[str]:
        """Live-route claims with more than one satisfied alternative --
        each one is a place the chain could be short-circuited."""
        return frozenset(
            cid for cid in self.live_route if len(self.satisfied_alternatives.get(cid, [])) > 1
        )


def solve(world: World, placement: Dict[str, Optional[str]], logic: AccessLogic) -> SolveResult:
    """`placement` maps claim_id -> slot_id, or claim_id -> None for
    evidence excluded from this run (used to test subsets)."""
    adj = build_adjacency(world, logic)
    reach_cache: Dict[str, Set[str]] = {}

    def reachable_from(slot_id: str) -> Set[str]:
        cached = reach_cache.get(slot_id)
        if cached is None:
            cached = bfs_reachable(adj, slot_id)
            reach_cache[slot_id] = cached
        return cached

    def live_alternatives(cid: str, slot_id: str, known: Set[str]) -> List[FrozenSet[str]]:
        """Alternatives for `cid` that are both fully known and fully able
        to reach `slot_id`."""
        out: List[FrozenSet[str]] = []
        for alt in world.claims[cid].support:
            if not alt <= known:
                continue
            # A claim in `known` always has a real slot: None-placed claims
            # can never enter `known`.
            if all(slot_id in reachable_from(placement[r]) for r in alt):
                out.append(alt)
        return out

    known: Set[str] = set()
    satisfied: Dict[str, List[FrozenSet[str]]] = {}
    used: Dict[str, FrozenSet[str]] = {}

    changed = True
    while changed:
        changed = False
        for cid, slot_id in placement.items():
            if cid in known or slot_id is None:
                continue
            claim = world.claims[cid]
            slot = world.slots[slot_id]
            if not logic.can_carry(world, slot, claim):
                continue
            alts = live_alternatives(cid, slot_id, known)
            if not alts:
                continue
            known.add(cid)
            satisfied[cid] = alts
            used[cid] = alts[0]
            changed = True

    # Re-scan once at the fixed point: an alternative may have become
    # satisfiable only after later claims were credited, and redundancy
    # detection must see the final `known` set, not a mid-iteration one.
    for cid in list(known):
        slot_id = placement[cid]
        assert slot_id is not None
        satisfied[cid] = live_alternatives(cid, slot_id, known)

    target_ids = set(world.target_ids())
    return SolveResult(
        known=known,
        solved=target_ids <= known,
        target_ids=target_ids,
        satisfied_alternatives=satisfied,
        used_alternative=used,
    )
