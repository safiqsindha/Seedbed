"""Cheatability check (component 5): confirm the solver FAILS on every
proper subset of the *load-bearing* evidence -- no shortcut exists.

What gets varied matters. An earlier revision varied the transitive
prerequisite closure under a purely conjunctive model, which made the check
vacuous: with AND-only support, dropping any chain claim breaks the chain by
construction, so `uncheatable` was a theorem about the data structure rather
than a measurement of the seed. Fed 2000 deliberately absurd placements it
never once returned False.

Two changes make it a real check:

  * Claims support disjunctive alternatives (see model.Support), so a target
    genuinely can have two independent routes. That is what a shortcut *is*,
    and it is now expressible.
  * The subsets varied are the solver's `live_route` -- the claims actually
    credited for reaching the target -- rather than every claim that could
    theoretically contribute. Distractors are *supposed* to be droppable;
    requiring otherwise would fail every world with a decoy in it.

Exhaustive checking is 2^n - 2 solver runs for n live-route claims, which is
cheap at toy sizes. Past `exhaustive_limit` it samples and says so in the
result -- never silently. Sampling always covers every single-claim removal
first (the cheapest, most direct "is this claim load-bearing" probe), then
draws randomly sized subsets, per arXiv:2510.11956's finding that
controlling which hops are covered -- rather than sampling uniformly -- is
what actually surfaces disconnected reasoning.
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
    live_route: FrozenSet[str]
    #: Live-route claims with more than one satisfied support alternative.
    #: Non-empty means the placement contains redundant support, which is
    #: the structural cause of every cheatable seed.
    redundant_support: FrozenSet[str]


def _subsets(
    ids: List[str], exhaustive: bool, rng: random.Random, sample_size: int
) -> Iterator[FrozenSet[str]]:
    n = len(ids)
    if exhaustive:
        for r in range(0, n):  # 0..n-1 elements: every proper subset
            for combo in itertools.combinations(ids, r):
                yield frozenset(combo)
        return

    for cid in ids:  # always check every single-claim removal
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

    route = full.live_route
    route_ids = sorted(route)
    exhaustive = len(route_ids) <= exhaustive_limit
    rng = random.Random(seed)

    checked = 0
    for subset in _subsets(route_ids, exhaustive, rng, sample_size):
        checked += 1
        sub_placement: Dict[str, Optional[str]] = dict(placement)
        for cid in route_ids:
            if cid not in subset:
                sub_placement[cid] = None
        if solve(world, sub_placement, logic).solved:
            return CheatabilityResult(
                uncheatable=False,
                exhaustive=exhaustive,
                subsets_checked=checked,
                counterexample=subset,
                live_route=route,
                redundant_support=full.redundantly_supported,
            )

    return CheatabilityResult(
        uncheatable=True,
        exhaustive=exhaustive,
        subsets_checked=checked,
        counterexample=None,
        live_route=route,
        redundant_support=full.redundantly_supported,
    )
