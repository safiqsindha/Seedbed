"""Ground truth for the recovery harness -- what seedbed's own reference
solver says about a placement, in exactly the shape `scoring.py` compares
a model's answer against.

Seedbed's own solver is the oracle. It defines the correct answer and the
live route; this module just gives that a stable, minimal shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

from seedbed.access import AccessLogic
from seedbed.model import World
from seedbed.solver import solve


@dataclass(frozen=True)
class Oracle:
    solved: bool
    target_id: str
    #: Claims actually load-bearing for the target (includes the target
    #: itself). Empty when unsolved.
    live_route: FrozenSet[str]


def compute_oracle(
    world: World, placement: Dict[str, Optional[str]], logic: AccessLogic
) -> Oracle:
    targets = world.target_ids()
    if len(targets) != 1:
        raise ValueError(
            f"harness assumes exactly one target claim per world, got {sorted(targets)}"
        )
    target_id = next(iter(targets))
    result = solve(world, placement, logic)
    return Oracle(solved=result.solved, target_id=target_id, live_route=result.live_route)
