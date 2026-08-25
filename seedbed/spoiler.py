"""Spoiler log (component 6): seed, every placement, the recovery path, and
the difficulty score, all reproducible from (world, tier, seed) alone.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict

from .access import AccessLogic, all_simple_paths, build_adjacency
from .cheat import check_cheatability
from .difficulty import recovery_edges
from .difficulty import score as score_difficulty
from .fill import assumed_fill
from .model import World
from .solver import solve

#: How many distinct simple paths to enumerate per recovery edge, and how
#: many of them to actually list. Counting is capped separately from listing
#: because a dense graph can carry hundreds of routes between two slots and
#: the log should stay readable while still reporting the true breadth.
PATH_COUNT_CAP = 200
PATH_LIST_CAP = 5


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

    # The shortest path is how the chain is *scored*; the full set of simple
    # paths is how a reader might actually trace it. Enumerating them is the
    # recursive-DFS port of the prior art's PathsToRegion (access.all_simple_paths),
    # and a spoiler log is exactly where it belongs: it shows every route the
    # evidence admits, not just the cheapest one.
    adj = build_adjacency(world, logic)
    recovery_path = []
    for supporter, cid, path in recovery_edges(world, fill_result.placement, logic):
        src, dst = fill_result.placement[supporter], fill_result.placement[cid]
        routes = all_simple_paths(adj, src, dst, cap=PATH_COUNT_CAP)
        capped = len(routes) >= PATH_COUNT_CAP
        recovery_path.append(
            {
                "from_claim": supporter,
                "from_label": world.claims[supporter].label,
                "to_claim": cid,
                "to_label": world.claims[cid].label,
                "slot_path": path,
                "hops": max(len(path) - 1, 0),
                "distinct_simple_paths": len(routes),
                # A capped count is a lower bound, and says so rather than
                # reading as an exact total.
                "distinct_simple_paths_is_lower_bound": capped,
                "example_alternate_paths": [r for r in routes if r != path][:PATH_LIST_CAP],
            }
        )

    return {
        "seed": seed,
        "tier": logic.name,
        "claim_order": fill_result.order,
        "placement": fill_result.placement,
        "rolls": [asdict(r) for r in fill_result.rolls],
        "search": {
            "nodes_explored": fill_result.nodes_explored,
            "backtracks": fill_result.backtracks,
            "solutions_compared": fill_result.solutions_compared,
            "solution_scores": fill_result.solution_scores,
            # Every RNG draw taken. With the seed, these fully determine the
            # search, so the run is explicable and not merely repeatable.
            "rng_draws": asdict(fill_result.rng_draws),
            # The whole search including the branches that were undone --
            # `rolls` above covers only the winning placement.
            "trace": [asdict(e) for e in fill_result.trace],
            "trace_truncated": fill_result.trace_truncated,
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


def dumps(
    world: World,
    logic: AccessLogic,
    seed: int,
    *,
    indent: int = 2,
    include_trace: bool = True,
) -> str:
    log = build_spoiler_log(world, logic, seed)
    if not include_trace:
        # The counts stay: dropping the trace should shrink the log, not
        # hide that a search happened.
        log["search"] = {k: v for k, v in log["search"].items() if k not in ("trace", "rng_draws")}
        log["search"]["trace_omitted"] = True
    return json.dumps(log, indent=indent, sort_keys=False)
