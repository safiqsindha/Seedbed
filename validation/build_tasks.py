"""Generate the recovery-harness task set.

Spans both bundled worlds and all three tiers, selecting seeds for wide
coverage of the difficulty scorer's output range rather than just the
easy/hard extremes. Everything is seeded and written to disk so the study
is re-runnable: `python -m validation.build_tasks` regenerates byte-identical
task files from the constants below.

Two task families:
  - main: the full placement, as `seedbed.generate` produced it.
  - ablation: the same placement with exactly one live-route (non-target)
    claim's placement removed -- Seedbed's own uncheatability guarantee
    means this must always flip the oracle to unsolved. Used by the
    spurious-success check (validation/spurious.py): a solver-under-test
    that still claims success on these is guessing from priors.

Run this before dispatching any model calls; it does no LLM calls itself.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from seedbed.access import TIERS
from seedbed.api import GeneratedSeed, build_world, generate
from seedbed.fill import FillError

from .facts import render_facts
from .oracle import Oracle, compute_oracle
from .prompt import build_prompt

DATA_DIR = Path(__file__).parent / "data"
TASKS_DIR = DATA_DIR / "tasks"
PROMPTS_DIR = DATA_DIR / "prompts"

WORLDS = ["toy", "relay"]
TIER_NAMES = ["easy", "standard", "hard"]

#: How many candidate seeds to try generating per (world, tier) before
#: picking from them. Generation is deterministic and cheap at this scale.
SEEDS_TO_TRY = range(60)

#: How many of the successfully generated seeds to keep per (world, tier),
#: chosen to spread across the observed difficulty range (not just
#: min/max) -- evenly spaced positions in the sorted-by-difficulty list.
SEEDS_TO_KEEP = 6

#: Of the kept seeds across the whole task set, how many (stratified by
#: difficulty) also get an ablation variant.
ABLATION_STRIDE = 3  # every 3rd seed, sorted by difficulty, gets ablated


def _task_id(world: str, tier: str, seed: int) -> str:
    return f"{world}_{tier}_{seed:03d}"


def _oracle_dict(o: Oracle) -> Dict[str, Any]:
    return {"solved": o.solved, "target_id": o.target_id, "live_route": sorted(o.live_route)}


def _write_task(task_id: str, facts: Dict[str, Any], oracle: Oracle, extra: Dict[str, Any]) -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    record = {"task_id": task_id, "facts": facts, "oracle": _oracle_dict(oracle), **extra}
    (TASKS_DIR / f"{task_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    (PROMPTS_DIR / f"{task_id}.txt").write_text(build_prompt(facts))


def _select_spread(candidates: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Evenly-spaced picks from `candidates` sorted by difficulty, so the
    kept set spans the observed range rather than clustering."""
    ordered = sorted(candidates, key=lambda c: c["difficulty"])
    n = len(ordered)
    if n <= k:
        return ordered
    idxs = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    return [ordered[i] for i in idxs]


def build_main_tasks() -> List[Dict[str, Any]]:
    manifest: List[Dict[str, Any]] = []
    for world_name in WORLDS:
        world = build_world(world_name)
        for tier_name in TIER_NAMES:
            logic = TIERS[tier_name]
            candidates = []
            for seed in SEEDS_TO_TRY:
                try:
                    result: GeneratedSeed = generate(world, tier=logic, seed=seed)
                except FillError:
                    continue
                candidates.append(
                    {
                        "world": world_name,
                        "tier": tier_name,
                        "seed": seed,
                        "difficulty": result.difficulty,
                        "breakdown": dict(result.difficulty_breakdown),
                        "result": result,
                    }
                )
            kept = _select_spread(candidates, SEEDS_TO_KEEP)
            for c in kept:
                result: GeneratedSeed = c["result"]
                facts = render_facts(
                    world, result.placement, logic, seed=c["seed"], world_name=world_name
                )
                oracle = compute_oracle(world, result.placement, logic)
                task_id = _task_id(world_name, tier_name, c["seed"])
                _write_task(
                    task_id,
                    facts,
                    oracle,
                    {
                        "kind": "main",
                        "difficulty": c["difficulty"],
                        "difficulty_breakdown": c["breakdown"],
                    },
                )
                manifest.append(
                    {
                        "task_id": task_id,
                        "world": world_name,
                        "tier": tier_name,
                        "seed": c["seed"],
                        "difficulty": c["difficulty"],
                        **{f"term_{k}": v for k, v in c["breakdown"].items()},
                    }
                )
    return manifest


def build_ablation_tasks(manifest: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ablation_manifest: List[Dict[str, Any]] = []
    ordered = sorted(manifest, key=lambda m: m["difficulty"])
    chosen = ordered[::ABLATION_STRIDE]
    for m in chosen:
        world = build_world(m["world"])
        logic = TIERS[m["tier"]]
        task = json.loads((TASKS_DIR / f"{m['task_id']}.json").read_text())
        # Reconstruct claim -> slot from the rendered facts' inverse mapping.
        placement: Dict[str, Any] = {}
        for slot in task["facts"]["slots"]:
            for cid in slot["claims_carried_here"]:
                placement[cid] = slot["id"]

        live_route = set(task["oracle"]["live_route"])
        target_id = task["oracle"]["target_id"]
        droppable = sorted(live_route - {target_id})
        if not droppable:
            continue  # nothing to ablate (shouldn't happen on a real target chain)
        rng = random.Random(m["seed"])
        drop_id = rng.choice(droppable)

        ablated_placement = dict(placement)
        ablated_placement[drop_id] = None
        facts = render_facts(
            world, ablated_placement, logic, seed=m["seed"], world_name=m["world"]
        )
        oracle = compute_oracle(world, ablated_placement, logic)
        task_id = f"{m['task_id']}_ablate_{drop_id}"
        _write_task(
            task_id,
            facts,
            oracle,
            {
                "kind": "ablation",
                "base_task_id": m["task_id"],
                "dropped_claim": drop_id,
                "difficulty": m["difficulty"],
            },
        )
        ablation_manifest.append(
            {
                "task_id": task_id,
                "base_task_id": m["task_id"],
                "world": m["world"],
                "tier": m["tier"],
                "seed": m["seed"],
                "dropped_claim": drop_id,
                "oracle_solved": oracle.solved,
            }
        )
    return ablation_manifest


def main() -> None:
    manifest = build_main_tasks()
    ablation_manifest = build_ablation_tasks(manifest)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    (DATA_DIR / "ablation_manifest.json").write_text(
        json.dumps(ablation_manifest, indent=2, sort_keys=True)
    )

    print(f"main tasks: {len(manifest)}")
    print(f"ablation tasks: {len(ablation_manifest)}")
    unsolved_ablations = [a for a in ablation_manifest if a["oracle_solved"]]
    if unsolved_ablations:
        print(
            f"WARNING: {len(unsolved_ablations)} ablation(s) remained solvable after dropping "
            "a live-route claim -- this would contradict the uncheatability guarantee:"
        )
        for a in unsolved_ablations:
            print(f"  {a['task_id']}")


if __name__ == "__main__":
    main()
