import pytest

from seedbed.access import TIERS
from seedbed.fill import UnsolvableWorldError, assumed_fill
from seedbed.model import Claim
from seedbed.toyworld import build_world

SEEDS = range(20)


def test_same_seed_is_byte_identical():
    world = build_world()
    logic = TIERS["standard"]
    a = assumed_fill(world, logic, seed=42)
    b = assumed_fill(world, logic, seed=42)
    assert a.placement == b.placement
    assert a.order == b.order
    assert [(r.claim_id, r.candidates, r.chosen, r.reason) for r in a.rolls] == [
        (r.claim_id, r.candidates, r.chosen, r.reason) for r in b.rolls
    ]


def test_different_seeds_can_diverge():
    world = build_world()
    logic = TIERS["standard"]
    placements = {tuple(sorted(assumed_fill(world, logic, seed=s).placement.items())) for s in SEEDS}
    assert len(placements) > 1, "seeded fill should explore more than one placement across 20 seeds"


def test_every_claim_gets_its_own_slot():
    world = build_world()
    for tier in TIERS.values():
        fr = assumed_fill(world, tier, seed=0)
        assert set(fr.placement) == set(world.claims)
        assert len(set(fr.placement.values())) == len(fr.placement), "no two claims share a slot"


def test_pathological_claim_cycle_fails_loudly():
    world = build_world()
    # c_bad requires itself: no topological order can ever place it.
    world.claims["c_bad"] = Claim("c_bad", "impossible", requires=frozenset({"c_bad"}))
    with pytest.raises(UnsolvableWorldError):
        assumed_fill(world, TIERS["standard"], seed=0)


def test_pathological_unreachable_authority_fails_loudly():
    world = build_world()
    # Only frank is exec-ranked; strip his slots so an exec-only claim has
    # nowhere legal to go.
    world.slots = {sid: s for sid, s in world.slots.items() if s.author != "frank"}
    world.claims["c_bad"] = Claim("c_bad", "impossible", requires=frozenset(), min_role="exec")
    with pytest.raises(UnsolvableWorldError):
        assumed_fill(world, TIERS["standard"], seed=0)
