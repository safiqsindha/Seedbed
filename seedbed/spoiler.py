"""Spoiler log (component 6): seed, every placement, the recovery path, and
the difficulty score, all reproducible from (world, tier, seed) alone.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict

from .access import AccessLogic, build_adjacency, shortest_path
from .cheat import check_cheatability
from .difficulty import score as score_difficulty
from .fill import assumed_fill
from .model import World
from .solver import solve


def build_spoiler_log(world: World, logic: AccessLogic, seed: int) -> Dict[str, Any]:
    fill_result = assumed_fill(world, logic, seed)

    solve_result = solve(world, fill_result.placement, logic)
    if not solve_result.solved:
        raise RuntimeError(
            "assumed_fill produced an unsolvable placement -- the solvability "
            "oracle must never fail on a generated seed"
        )

    cheat_result = check_cheatability(world, fill_result.placement, logic, seed)
    difficulty = score_difficulty(world, fill_result.placement, logic)

    adj = build_adjacency(world, logic)
    chain_ids = sorted(world.chain_claim_ids())
    recovery_path = []
    for cid in chain_ids:
        claim = world.claims[cid]
        slot_id = fill_result.placement[cid]
        paths_from_prereqs = {
            req: shortest_path(adj, fill_result.placement[req], slot_id) for req in sorted(claim.requires)
        }
        recovery_path.append(
            {
                "claim": cid,
                "label": claim.label,
                "slot": slot_id,
                "requires": sorted(claim.requires),
                "paths_from_prereqs": paths_from_prereqs,
            }
        )

    return {
        "seed": seed,
        "tier": logic.name,
        "claim_order": fill_result.order,
        "placement": fill_result.placement,
        "rolls": [asdict(r) for r in fill_result.rolls],
        "solvable": solve_result.solved,
        "known_claims": sorted(solve_result.known),
        "uncheatable": cheat_result.uncheatable,
        "cheatability_checked": cheat_result.subsets_checked,
        "cheatability_exhaustive": cheat_result.exhaustive,
        "recovery_path": recovery_path,
        "difficulty": asdict(difficulty),
    }


def dumps(world: World, logic: AccessLogic, seed: int, *, indent: int = 2) -> str:
    return json.dumps(build_spoiler_log(world, logic, seed), indent=indent, sort_keys=False)
