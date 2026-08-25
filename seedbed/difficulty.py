"""Difficulty scorer (component 6): hop count + authority reversals crossed
+ distractor density along the path + low-salience carrier fraction.
Weights are tunable and echoed into the spoiler log, so a score is always
reproducible from (seed, tier, weights).

Everything is measured over the solver's **live route** -- the claims
actually credited for reaching the target -- rather than over every claim
that could theoretically contribute. Scoring the potential chain would let
unreachable decoys inflate the number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .access import EASY, AccessLogic, build_adjacency, shortest_path
from .model import ROLE_RANK, World
from .solver import solve

DEFAULT_WEIGHTS: Dict[str, float] = {
    "hop_count": 3.0,
    "authority_reversal": 4.0,
    "distractor_density": 1.0,
    "low_salience_fraction": 1.0,
}


@dataclass
class DifficultyScore:
    total: float
    hop_count: int
    authority_reversals: int
    distractor_density: float
    low_salience_fraction: float
    weights: Dict[str, float]


def recovery_edges(
    world: World, placement: Dict[str, str], logic: AccessLogic
) -> List[Tuple[str, str, List[str]]]:
    """(supporting_claim, supported_claim, slot_path) for every edge of the
    live route, in deterministic order."""
    result = solve(world, placement, logic)
    if not result.solved:
        return []
    adj = build_adjacency(world, logic)
    edges = []
    for cid in sorted(result.live_route):
        for supporter in sorted(result.used_alternative.get(cid, frozenset())):
            path = shortest_path(adj, placement[supporter], placement[cid])
            edges.append((supporter, cid, path or []))
    return edges


def score(
    world: World,
    placement: Dict[str, str],
    logic: AccessLogic,
    weights: Optional[Dict[str, float]] = None,
    decoy_reference_logic: AccessLogic = EASY,
) -> DifficultyScore:
    """`decoy_reference_logic` fixes the lens used to judge which decoys sit
    "near" the recovery path, and deliberately does *not* follow `logic`.

    A reader does not know the access rules -- inferring them is the task --
    so a decoy one permissive hop off the path can mislead regardless of the
    tier being graded. Scoring decoy proximity under `logic` also made the
    component fall as strictness rose (stricter logic prunes edges, so fewer
    decoys stay adjacent), which fought hop_count and left the total
    non-monotonic across tiers on 19 of 56 fixed placements. Holding the
    lens fixed removes that conflict without hiding it.
    """
    weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
    adj = build_adjacency(world, logic)
    decoy_adj = build_adjacency(world, decoy_reference_logic)
    result = solve(world, placement, logic)
    route = result.live_route
    edges = recovery_edges(world, placement, logic)

    route_slot_ids = {placement[cid] for cid in route}
    # Claims that are placed but not load-bearing: the decoys a reader can
    # be lured onto.
    decoy_slot_ids = {
        slot_id for cid, slot_id in placement.items() if cid not in route and slot_id is not None
    }

    hop_count = 0
    authority_reversals = 0
    path_slots: List[str] = []

    for supporter, cid, path in edges:
        if path:
            hop_count += len(path) - 1
            path_slots.extend(path)
        supporter_role = world.actors[world.slots[placement[supporter]].author].role
        carrier_role = world.actors[world.slots[placement[cid]].author].role
        if ROLE_RANK[carrier_role] < ROLE_RANK[supporter_role]:
            authority_reversals += 1

    # How thick is the decoy field around the real evidence? For each
    # load-bearing carrier, how many of its neighbours carry a
    # non-load-bearing claim.
    #
    # Two earlier definitions were worse. Counting *empty filler* slots
    # between evidence gave 1.0 on literally every seed -- a constant, and
    # so dead weight in the score. Normalising by recovery-path length then
    # made it a rate that could dilute as the path grew, so the total dipped
    # under stricter tiers even though the absolute decoy count rose.
    # Normalising by carrier count keeps the "per piece of real evidence"
    # reading and a denominator that does not move with path length.
    if route_slot_ids:
        brushes = sum(
            1
            for slot_id in route_slot_ids
            for nb in decoy_adj.get(slot_id, ())
            if nb in decoy_slot_ids
        )
        distractor_density = brushes / len(route_slot_ids)
    else:
        distractor_density = 0.0

    if route_slot_ids:
        low_salience_fraction = sum(
            1 for sid in route_slot_ids if world.slots[sid].salience == "low"
        ) / len(route_slot_ids)
    else:
        low_salience_fraction = 0.0

    total = (
        weights["hop_count"] * hop_count
        + weights["authority_reversal"] * authority_reversals
        + weights["distractor_density"] * distractor_density
        + weights["low_salience_fraction"] * low_salience_fraction
    )

    return DifficultyScore(
        total=total,
        hop_count=hop_count,
        authority_reversals=authority_reversals,
        distractor_density=distractor_density,
        low_salience_fraction=low_salience_fraction,
        weights=weights,
    )
