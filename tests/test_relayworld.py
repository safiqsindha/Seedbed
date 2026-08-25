"""The core invariants, re-run against a second, structurally different world.

Everything the project verified before this existed was a statement about
one topology. The relay world differs where it matters: a deeper chain, the
disjunction at the target rather than mid-chain, a two-level reporting
hierarchy, and authority gates stacked along the chain.
"""

from seedbed.access import TIERS
from seedbed.cheat import check_cheatability
from seedbed.fill import assumed_fill
from seedbed.relayworld import build_world
from seedbed.solver import solve

SEEDS = range(12)


def test_world_shape_differs_from_the_toy_world():
    from seedbed.toyworld import build_world as toy

    world, other = build_world(), toy()
    assert len(world.claims) != len(other.claims)
    # Disjunction sits at the target here, mid-chain there.
    assert len(world.claims["e5"].support) == 2
    assert world.claims["e5"].target
    assert not any(len(c.support) > 1 and c.target for c in other.claims.values())


def test_every_seed_is_solvable_and_uncheatable():
    world = build_world()
    for tier_name, logic in TIERS.items():
        for seed in SEEDS:
            result = assumed_fill(world, logic, seed=seed)
            solved = solve(world, result.placement, logic)
            assert solved.solved, (tier_name, seed)
            cheat = check_cheatability(world, result.placement, logic, seed=seed)
            assert cheat.uncheatable, (tier_name, seed, cheat.counterexample)
            assert not cheat.redundant_support


def test_both_support_routes_to_the_target_get_used():
    """If only one route ever wins, the disjunction is decoration."""
    world = build_world()
    routes = set()
    for logic in TIERS.values():
        for seed in range(40):
            result = assumed_fill(world, logic, seed=seed)
            routes.add(frozenset(solve(world, result.placement, logic).live_route))
    via_e4 = any("e4" in r for r in routes)
    via_e4b = any("e4b" in r for r in routes)
    assert via_e4 and via_e4b, routes


def test_access_logic_is_respected_for_every_placed_claim():
    world = build_world()
    for logic in TIERS.values():
        result = assumed_fill(world, logic, seed=0)
        for cid, slot_id in result.placement.items():
            assert logic.can_carry(world, world.slots[slot_id], world.claims[cid])


def test_same_seed_is_byte_identical():
    world = build_world()
    a = assumed_fill(world, TIERS["standard"], seed=7)
    b = assumed_fill(world, TIERS["standard"], seed=7)
    assert a.placement == b.placement
    assert [(r.claim_id, r.chosen) for r in a.rolls] == [(r.claim_id, r.chosen) for r in b.rolls]
