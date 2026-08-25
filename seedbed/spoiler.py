"""Spoiler log (component 6): seed, every placement, the recovery path, and
the difficulty score, all reproducible from (world, tier, seed) alone.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict

from .access import AccessLogic
from .cheat import check_cheatability
from .difficulty import recovery_edges
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
    if not cheat_result.uncheatable:
        raise RuntimeError(
            f"assumed_fill produced a cheatable placement (recoverable from subset "
            f"{sorted(cheat_result.counterexample or ())}) -- the fill's "
            "single-live-alternative invariant should make this impossible"
        )

    difficulty = score_difficulty(world, fill_result.placement, logic)
    route = sorted(solve_result.live_route)

    recovery_path = [
        {
            "from_claim": supporter,
            "from_label": world.claims[supporter].label,
            "to_claim": cid,
            "to_label": world.claims[cid].label,
            "slot_path": path,
            "hops": max(len(path) - 1, 0),
        }
        for supporter, cid, path in recovery_edges(world, fill_result.placement, logic)
    ]

    return {
        "seed": seed,
        "tier": logic.name,
        "claim_order": fill_result.order,
        "placement": fill_result.placement,
        "rolls": [asdict(r) for r in fill_result.rolls],
        "search": {
            "nodes_explored": fill_result.nodes_explored,
            "backtracks": fill_result.backtracks,
        },
        "solvable": solve_result.solved,
        "known_claims": sorted(solve_result.known),
        "live_route": route,
        "stranded_claims": sorted(set(fill_result.placement) - set(route)),
        "uncheatable": cheat_result.uncheatable,
        "cheatability_checked": cheat_result.subsets_checked,
        "cheatability_exhaustive": cheat_result.exhaustive,
        "redundant_support": sorted(cheat_result.redundant_support),
        "recovery_path": recovery_path,
        "difficulty": asdict(difficulty),
    }


def dumps(world: World, logic: AccessLogic, seed: int, *, indent: int = 2) -> str:
    return json.dumps(build_spoiler_log(world, logic, seed), indent=indent, sort_keys=False)
