"""Ingest solver-under-test answers, score them against the oracle, and
correlate accuracy against `difficulty` -- overall and per scoring term.

No numpy/scipy dependency (seedbed itself has zero dependencies; this stays
consistent with that rather than adding one for two formulas). Pearson and
Spearman are both a few lines of pure Python.

Usage:
    python -m validation.analyze                 # main study
    python -m validation.analyze --ablation       # spurious-success check
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .oracle import Oracle
from .scoring import Score, score_answer

DATA_DIR = Path(__file__).parent / "data"
TASKS_DIR = DATA_DIR / "tasks"
ANSWERS_DIR = DATA_DIR / "answers"


def _load_oracle(task: Dict[str, Any]) -> Oracle:
    o = task["oracle"]
    return Oracle(solved=o["solved"], target_id=o["target_id"], live_route=frozenset(o["live_route"]))


def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = sum((x - mx) ** 2 for x in xs) ** 0.5
    deny = sum((y - my) ** 2 for y in ys) ** 0.5
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def _rank(values: List[float]) -> List[float]:
    """Average (fractional) ranks, ties split evenly -- standard Spearman
    tie handling."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-indexed
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    return pearson(_rank(xs), _rank(ys))


def load_answers_for_task(task_id: str) -> List[Dict[str, Any]]:
    answers = []
    for f in sorted(ANSWERS_DIR.glob(f"{task_id}_attempt*.json")):
        try:
            answers.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            print(f"WARNING: unparseable answer file {f}, skipping")
    return answers


def collect_main_rows() -> List[Dict[str, Any]]:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text())
    rows = []
    for m in manifest:
        task = json.loads((TASKS_DIR / f"{m['task_id']}.json").read_text())
        oracle = _load_oracle(task)
        answers = load_answers_for_task(m["task_id"])
        if not answers:
            continue
        scores: List[Score] = [score_answer(oracle, a) for a in answers]
        binary_acc = statistics.fmean(1.0 if s.binary_correct else 0.0 for s in scores)
        f1_scores = [s.f1 for s in scores if s.f1 is not None]
        mean_f1 = statistics.fmean(f1_scores) if f1_scores else None
        rows.append(
            {
                "task_id": m["task_id"],
                "world": m["world"],
                "tier": m["tier"],
                "difficulty": m["difficulty"],
                "n_attempts": len(answers),
                "binary_accuracy": binary_acc,
                "mean_f1": mean_f1,
                **{k: v for k, v in m.items() if k.startswith("term_")},
            }
        )
    return rows


def correlate(rows: List[Dict[str, Any]], x_key: str, y_key: str) -> Tuple[Optional[float], Optional[float], int]:
    pairs = [(r[x_key], r[y_key]) for r in rows if r.get(y_key) is not None]
    if len(pairs) < 2:
        return None, None, len(pairs)
    xs, ys = zip(*pairs)
    return pearson(list(xs), list(ys)), spearman(list(xs), list(ys)), len(pairs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default=str(DATA_DIR / "results.csv"))
    args = parser.parse_args()

    rows = collect_main_rows()
    if not rows:
        print("No answers found yet under validation/data/answers/. Nothing to analyze.")
        return

    # --- write the raw per-task table ---
    term_keys = sorted({k for r in rows for k in r if k.startswith("term_")})
    fieldnames = [
        "task_id", "world", "tier", "difficulty", "n_attempts", "binary_accuracy", "mean_f1"
    ] + term_keys
    import csv as _csv

    with open(args.csv, "w", newline="") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
    print(f"wrote {len(rows)} rows to {args.csv}")

    # --- overall correlation ---
    r_p, r_s, n = correlate(rows, "difficulty", "binary_accuracy")
    print(f"\n=== difficulty vs binary_accuracy (n={n}) ===")
    print(f"Pearson r  = {r_p}")
    print(f"Spearman r = {r_s}")

    f1_rows = [r for r in rows if r["mean_f1"] is not None]
    r_p, r_s, n = correlate(f1_rows, "difficulty", "mean_f1")
    print(f"\n=== difficulty vs mean_f1 (n={n}) ===")
    print(f"Pearson r  = {r_p}")
    print(f"Spearman r = {r_s}")

    # --- per-term breakdown ---
    print("\n=== per-term correlation with binary_accuracy ===")
    for term in term_keys:
        r_p, r_s, n = correlate(rows, term, "binary_accuracy")
        print(f"{term:35s} n={n:3d}  Pearson={r_p}  Spearman={r_s}")

    # --- scatter (ascii, sorted by difficulty) ---
    print("\n=== scatter: difficulty -> binary_accuracy, sorted ===")
    for r in sorted(rows, key=lambda r: r["difficulty"]):
        bar = "#" * round(r["binary_accuracy"] * 20)
        print(f"{r['task_id']:22s} diff={r['difficulty']:6.2f} acc={r['binary_accuracy']:.2f} {bar}")


if __name__ == "__main__":
    main()
