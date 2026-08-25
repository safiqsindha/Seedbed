"""Cheatability check (component 5): confirm the solver FAILS on every
proper subset of the placed chain evidence -- no shortcut exists.

Only chain claims (the transitive requires-closure of the target) are ever
varied: distractor claims never appear in any target's requires-closure by
definition, so including or excluding them from a subset can never change
whether the target is recoverable. Restricting subset generation to chain
claims is therefore an exact simplification, not an approximation.

Exhaustive subset checking is 2^n - 2 runs for n pieces of chain evidence;
tractable for small worlds. Past `exhaustive_limit`, sampling is used and
the fact is recorded in the result -- never silently assumed. The sampling
strategy always checks every single-item removal (the cheapest, most
direct "is this one piece of evidence load-bearing" test) plus randomly
sized subsets, per arXiv:2510.11956's finding that controlling which hops
are covered -- not uniform random coverage -- is what actually surfaces
disconnected-reasoning shortcuts.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterator, List, Optional

from .access import AccessLogic
from .model import World
from .solver import solve

EXHAUSTIVE_LIMIT = 12  # 2**12 - 2 = 4094 proper subsets; still cheap to run


@dataclass
class CheatabilityResult:
    uncheatable: bool
    exhaustive: bool
    subsets_checked: int
    counterexample: Optional[FrozenSet[str]]


def _subsets(
    ids: List[str], exhaustive: bool, rng: random.Random, sample_size: int
) -> Iterator[FrozenSet[str]]:
    n = len(ids)
    if exhaustive:
        for r in range(0, n):  # 0..n-1 elements: every proper subset
            for combo in itertools.combinations(ids, r):
                yield frozenset(combo)
        return

    for cid in ids:  # always check every single-item removal
        yield frozenset(ids) - {cid}
    for _ in range(sample_size):
        k = rng.randint(0, n - 1)
        yield frozenset(rng.sample(ids, k))


def check_cheatability(
    world: World,
    placement: Dict[str, str],
    logic: AccessLogic,
    seed: int,
    sample_size: int = 200,
    exhaustive_limit: int = EXHAUSTIVE_LIMIT,
) -> CheatabilityResult:
    full = solve(world, placement, logic)
    if not full.solved:
        raise ValueError("placement is not solvable; cheatability is undefined until it is")

    chain_ids = sorted(world.chain_claim_ids())
    exhaustive = len(chain_ids) <= exhaustive_limit
    rng = random.Random(seed)

    checked = 0
    for subset in _subsets(chain_ids, exhaustive, rng, sample_size):
        checked += 1
        sub_placement = dict(placement)
        for cid in chain_ids:
            if cid not in subset:
                sub_placement[cid] = None
        result = solve(world, sub_placement, logic)
        if result.solved:
            return CheatabilityResult(
                uncheatable=False,
                exhaustive=exhaustive,
                subsets_checked=checked,
                counterexample=subset,
            )

    return CheatabilityResult(
        uncheatable=True, exhaustive=exhaustive, subsets_checked=checked, counterexample=None
    )
