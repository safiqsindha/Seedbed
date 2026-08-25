"""Seedbed: seeded, solvability-guaranteed evidence placement for reasoning benchmarks.

Plug-in usage:

    from seedbed import generate, build_world

    result = generate(build_world("toy"), tier="hard", seed=7)
    result.placement      # claim id -> slot id
    result.live_route     # the claims that actually carry the inference
    result.difficulty     # tunable score

`seedbed.api` is the supported surface; everything else is internals and may
change. See `docs/PRIOR_ART_REPORT.md` for what is and is not guaranteed.
"""

from .access import EASY, HARD, STANDARD, TIERS, AccessLogic
from .api import (
    FillError,
    GeneratedSeed,
    RecoveryStep,
    SearchBudgetExceeded,
    UnsolvableWorldError,
    available_tiers,
    available_worlds,
    build_world,
    generate,
    register_world,
)
from .model import ROOT, Actor, Claim, Slot, World, either, requires

__all__ = [
    # public API
    "generate",
    "GeneratedSeed",
    "RecoveryStep",
    "build_world",
    "register_world",
    "available_worlds",
    "available_tiers",
    # errors
    "FillError",
    "UnsolvableWorldError",
    "SearchBudgetExceeded",
    # authoring a world
    "Actor",
    "Claim",
    "Slot",
    "World",
    "ROOT",
    "requires",
    "either",
    # access logic
    "AccessLogic",
    "TIERS",
    "EASY",
    "STANDARD",
    "HARD",
]
