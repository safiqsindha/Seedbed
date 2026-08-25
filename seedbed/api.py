"""Seedbed's public interface — the surface other programs plug into.

Everything else in the package is machinery. This module is the contract:
one call in, one frozen result out, plus the types a consumer needs to
supply its own world or read a generated seed.

    from seedbed import generate, TIERS

    seed = generate(my_world, tier="standard", seed=7)
    for claim_id, slot_id in seed.placement.items():
        render(my_world.slots[slot_id], my_world.claims[claim_id])

A consumer never needs to know about fill order, backtracking, or the
solver's fixed point. It needs: where each claim went, which ones are
load-bearing, how hard the result is, and whether the engine stands behind
it. `GeneratedSeed` carries exactly that, and nothing that would change
meaning if the internals were rewritten.

Rendering, prose, and LLM integration live on the far side of this line by
design (they are the project's stated non-goals). A renderer consumes
`GeneratedSeed`; it does not reach into the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, Optional

from .access import TIERS, AccessLogic
from .cheat import check_cheatability
from .difficulty import DEFAULT_WEIGHTS, recovery_edges
from .difficulty import score as _score
from .fill import (
    DEFAULT_IMPROVEMENT_PATIENCE,
    DEFAULT_NODE_BUDGET,
    DEFAULT_SOLUTION_LIMIT,
    DEFAULT_TRACE_LIMIT,
    FillError,
    SearchBudgetExceeded,
    UnsolvableWorldError,
    assumed_fill,
)
from .model import World
from .solver import solve
from .spoiler import build_spoiler_log

__all__ = [
    "GeneratedSeed",
    "RecoveryStep",
    "generate",
    "available_tiers",
    "register_world",
    "available_worlds",
    "build_world",
    "FillError",
    "UnsolvableWorldError",
    "SearchBudgetExceeded",
]


@dataclass(frozen=True)
class RecoveryStep:
    """One inference a solver must make to get from evidence to target."""

    from_claim: str
    to_claim: str
    slot_path: List[str]
    hops: int


@dataclass(frozen=True)
class GeneratedSeed:
    """A placement plus everything a consumer needs to trust and use it."""

    seed: int
    tier: str
    #: claim id -> slot id. Every claim is placed.
    placement: Mapping[str, str]
    #: Claims actually load-bearing for the target.
    live_route: FrozenSet[str]
    #: Placed but not load-bearing -- the decoys.
    stranded: FrozenSet[str]
    #: Inference steps from evidence to target, in order.
    recovery: List[RecoveryStep]
    difficulty: float
    difficulty_breakdown: Mapping[str, float]
    #: The engine's own verdicts on this seed. Both are always checked;
    #: `generate` raises rather than returning a seed where either fails.
    solvable: bool
    uncheatable: bool
    #: True when uncheatability was established by sampling rather than by
    #: exhaustive subset checking. Never silently assumed.
    uncheatability_sampled: bool
    subsets_checked: int
    #: Search cost, for callers tuning budgets.
    nodes_explored: int
    solutions_compared: int

    def slots_for(self, world: World) -> Dict[str, Any]:
        """claim id -> the Slot object carrying it."""
        return {cid: world.slots[sid] for cid, sid in self.placement.items()}

    def spoiler(self, world: World) -> Dict[str, Any]:
        """The full spoiler log, including the complete search trace.

        Kept as a method rather than a field: it is large, and most
        consumers want the placement, not the audit trail.
        """
        return build_spoiler_log(world, TIERS[self.tier], self.seed)


def available_tiers() -> List[str]:
    return sorted(TIERS)


def generate(
    world: World,
    tier: str | AccessLogic = "standard",
    seed: int = 0,
    *,
    weights: Optional[Mapping[str, float]] = None,
    node_budget: int = DEFAULT_NODE_BUDGET,
    solution_limit: int = DEFAULT_SOLUTION_LIMIT,
    improvement_patience: int = DEFAULT_IMPROVEMENT_PATIENCE,
    trace_limit: int = DEFAULT_TRACE_LIMIT,
) -> GeneratedSeed:
    """Place `world`'s claims and return a verified seed.

    Raises `UnsolvableWorldError` when no legal placement exists, and
    `SearchBudgetExceeded` when the search ran out of budget without
    deciding — these mean different things and are deliberately distinct
    types. Both derive from `FillError` if you only care that it failed.

    The returned seed is always solvable and uncheatable: those are checked
    here, and a failure raises rather than returning a seed that quietly
    does not hold.
    """
    logic = tier if isinstance(tier, AccessLogic) else TIERS[tier]

    result = assumed_fill(
        world,
        logic,
        seed,
        node_budget=node_budget,
        solution_limit=solution_limit,
        trace_limit=trace_limit,
        improvement_patience=improvement_patience,
    )

    solved = solve(world, result.placement, logic)
    if not solved.solved:
        raise RuntimeError(
            "generated placement failed the solvability oracle; this is an engine bug, "
            "not a property of the world"
        )

    cheat = check_cheatability(world, result.placement, logic, seed)
    if not cheat.uncheatable:
        raise RuntimeError(
            f"generated placement is recoverable from the proper subset "
            f"{sorted(cheat.counterexample or ())}; this is an engine bug"
        )

    breakdown = _score(world, result.placement, logic, weights=dict(weights) if weights else None)

    return GeneratedSeed(
        seed=seed,
        tier=logic.name,
        placement=dict(result.placement),
        live_route=solved.live_route,
        stranded=frozenset(result.placement) - solved.live_route,
        recovery=[
            RecoveryStep(
                from_claim=a, to_claim=b, slot_path=list(path), hops=max(len(path) - 1, 0)
            )
            for a, b, path in recovery_edges(world, result.placement, logic)
        ],
        difficulty=breakdown.total,
        difficulty_breakdown={
            "hop_count": float(breakdown.hop_count),
            "authority_reversals": float(breakdown.authority_reversals),
            "distractor_density": breakdown.distractor_density,
            "low_salience_fraction": breakdown.low_salience_fraction,
        },
        solvable=True,
        uncheatable=True,
        uncheatability_sampled=not cheat.exhaustive,
        subsets_checked=cheat.subsets_checked,
        nodes_explored=result.nodes_explored,
        solutions_compared=result.solutions_compared,
    )


# --- world registry -------------------------------------------------------
#
# So a consumer can ship its own world and address it by name, the way the
# CLI addresses the bundled ones, without importing engine internals.

_WORLDS: Dict[str, Callable[[], World]] = {}


def register_world(name: str, builder: Callable[[], World]) -> None:
    """Register a zero-argument builder under `name`."""
    _WORLDS[name] = builder


def available_worlds() -> List[str]:
    return sorted(_WORLDS)


def build_world(name: str) -> World:
    try:
        return _WORLDS[name]()
    except KeyError:
        raise KeyError(f"unknown world {name!r}; available: {available_worlds()}") from None


def _register_bundled() -> None:
    from . import relayworld, toyworld

    register_world("toy", toyworld.build_world)
    register_world("relay", relayworld.build_world)


_register_bundled()
