"""Score a solver-under-test's answer against the oracle.

Two scores, deliberately kept separate rather than blended, because the
study is designed to let them diverge:

  - `binary_correct`: did the model get the yes/no right -- is the target
    claim actually recoverable from this placement?
  - `f1` (and precision/recall): when the target *is* recoverable, did the
    model's stated supporting chain match the live route, or did it land
    on the right answer through the wrong (or no) reasoning?
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, Mapping, Optional

from .oracle import Oracle


@dataclass(frozen=True)
class Score:
    binary_correct: bool
    precision: Optional[float]
    recall: Optional[float]
    f1: Optional[float]
    predicted_solved: bool
    predicted_chain: FrozenSet[str]


def score_answer(oracle: Oracle, answer: Mapping[str, Any]) -> Score:
    predicted_solved = bool(answer.get("target_known", False))
    predicted_chain = frozenset(answer.get("chain") or ())
    binary_correct = predicted_solved == oracle.solved

    if not oracle.solved:
        # Nothing to compare a chain against -- there is no live route.
        return Score(binary_correct, None, None, None, predicted_solved, predicted_chain)

    true_set = oracle.live_route
    pred_set = predicted_chain if predicted_solved else frozenset()
    tp = len(true_set & pred_set)
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(true_set) if true_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return Score(binary_correct, precision, recall, f1, predicted_solved, predicted_chain)
