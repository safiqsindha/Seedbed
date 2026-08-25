"""Difficulty scorer (component 6): hop count + authority reversals crossed
+ distractor density along the path + low-salience carrier fraction.
Weights are tunable and passed through to the spoiler log so a score is
always reproducible from (seed, tier, weights).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .access import AccessLogic, build_adjacency, shortest_path
from .model import ROLE_RANK, World

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


def score(
    world: World,
    placement: Dict[str, str],
    logic: AccessLogic,
    weights: Optional[Dict[str, float]] = None,
) -> DifficultyScore:
    weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
    adj = build_adjacency(world, logic)
    chain_ids = sorted(world.chain_claim_ids())

    evidence_slot_ids = {placement[cid] for cid in chain_ids}
    hop_count = 0
    authority_reversals = 0
    intermediate_slots: list[str] = []

    for cid in chain_ids:
        claim = world.claims[cid]
        slot_id = placement[cid]
        slot = world.slots[slot_id]
        for req in claim.requires:
            prereq_slot_id = placement[req]
            path = shortest_path(adj, prereq_slot_id, slot_id)
            if path:
                hop_count += len(path) - 1
                intermediate_slots.extend(path[1:-1])
            prereq_author = world.actors[world.slots[prereq_slot_id].author]
            this_author = world.actors[slot.author]
            if ROLE_RANK[this_author.role] < ROLE_RANK[prereq_author.role]:
                authority_reversals += 1

    if intermediate_slots:
        non_evidence = sum(1 for sid in intermediate_slots if sid not in evidence_slot_ids)
        distractor_density = non_evidence / len(intermediate_slots)
    else:
        distractor_density = 0.0

    if evidence_slot_ids:
        low_salience_fraction = sum(
            1 for sid in evidence_slot_ids if world.slots[sid].salience == "low"
        ) / len(evidence_slot_ids)
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
