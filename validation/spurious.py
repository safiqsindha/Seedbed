"""Spurious-success check (section 3 of the study).

Seedbed's uncheatability guarantee is structural: no proper subset of the
live route recovers the target (checked exhaustively or by sampling at
generation time, see seedbed.cheat). `build_tasks.py`'s ablation family
leans on the single-claim-removal case of that guarantee, which is always
checked and always holds -- so every ablated task has a ground truth of
"not recoverable" by construction.

This module asks the empirical question TRACE asked of real models: does a
solver-under-test still claim success anyway? If it does, that is spurious
guessing (arriving at the target from priors / pattern-matching rather than
from the actual evidence), and the rate at which it happens is a correction
factor on every accuracy number in analyze.py -- those numbers are inflated
by exactly this rate to the extent the same guessing behavior occurs on
solvable placements too (which this check cannot directly see, since there
the correct answer and a guess are indistinguishable from the outside).
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List

from .analyze import load_answers_for_task
from .oracle import Oracle
from .scoring import score_answer

DATA_DIR = Path(__file__).parent / "data"
TASKS_DIR = DATA_DIR / "tasks"


def main() -> None:
    manifest = json.loads((DATA_DIR / "ablation_manifest.json").read_text())
    rows: List[Dict[str, Any]] = []
    for m in manifest:
        task = json.loads((TASKS_DIR / f"{m['task_id']}.json").read_text())
        o = task["oracle"]
        assert o["solved"] is False, (
            f"{m['task_id']}: ablated task must be unsolvable by construction "
            "(uncheatability guarantee) -- this indicates a harness bug, not a model result"
        )
        oracle = Oracle(solved=False, target_id=o["target_id"], live_route=frozenset())

        answers = load_answers_for_task(m["task_id"])
        if not answers:
            continue
        scores = [score_answer(oracle, a) for a in answers]
        # A "spurious success" is the model claiming target_known despite
        # the true answer being unrecoverable.
        spurious = [not s.binary_correct for s in scores]  # binary_correct False <=> claimed known
        rows.append(
            {
                "task_id": m["task_id"],
                "base_task_id": m["base_task_id"],
                "world": m["world"],
                "tier": m["tier"],
                "dropped_claim": m["dropped_claim"],
                "n_attempts": len(answers),
                "spurious_rate": statistics.fmean(spurious),
            }
        )

    if not rows:
        print("No ablation answers found yet under validation/data/answers/.")
        return

    total_attempts = sum(r["n_attempts"] for r in rows)
    total_spurious = sum(r["spurious_rate"] * r["n_attempts"] for r in rows)
    overall_rate = total_spurious / total_attempts if total_attempts else 0.0

    print(f"=== spurious-success rate ({len(rows)} ablated seeds, {total_attempts} attempts) ===")
    print(f"overall: {overall_rate:.1%}\n")
    for r in sorted(rows, key=lambda r: -r["spurious_rate"]):
        flag = "  <-- spurious" if r["spurious_rate"] > 0 else ""
        print(
            f"{r['task_id']:35s} dropped={r['dropped_claim']:5s} "
            f"rate={r['spurious_rate']:.2f} ({r['n_attempts']} attempts){flag}"
        )

    with open(DATA_DIR / "spurious_results.json", "w") as f:
        json.dump({"overall_rate": overall_rate, "rows": rows}, f, indent=2)


if __name__ == "__main__":
    main()
