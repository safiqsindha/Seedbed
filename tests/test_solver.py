from seedbed.access import TIERS
from seedbed.fill import assumed_fill
from seedbed.solver import solve
from seedbed.toyworld import build_world

SEEDS = range(25)


def test_every_generated_seed_is_solvable():
    world = build_world()
    for tier_name, logic in TIERS.items():
        for seed in SEEDS:
            fr = assumed_fill(world, logic, seed=seed)
            result = solve(world, fr.placement, logic)
            assert result.solved, f"seed={seed} tier={tier_name} placement={fr.placement} not solvable"
            assert result.target_ids <= result.known


def test_solver_fails_when_a_required_claim_is_missing():
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)

    missing_c2 = dict(fr.placement)
    missing_c2["c2"] = None
    result = solve(world, missing_c2, logic)

    assert not result.solved
    assert "c2" not in result.known
    # c3 and c4 both transitively depend on c2, so neither can be recovered.
    assert "c3" not in result.known
    assert "c4" not in result.known
