from seedbed.access import TIERS
from seedbed.cheat import check_cheatability
from seedbed.fill import assumed_fill
from seedbed.toyworld import build_world

SEEDS = range(15)


def test_every_generated_seed_is_uncheatable_exhaustively():
    world = build_world()
    for tier_name, logic in TIERS.items():
        for seed in SEEDS:
            fr = assumed_fill(world, logic, seed=seed)
            result = check_cheatability(world, fr.placement, logic, seed=seed)
            assert result.exhaustive, "toy world's 4-claim chain should always be checked exhaustively"
            assert result.uncheatable, (
                f"seed={seed} tier={tier_name} placement={fr.placement} "
                f"was recoverable from a proper subset: {result.counterexample}"
            )


def test_sampled_mode_is_used_and_documented_above_the_limit():
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)
    # Force the sampled path even though the toy world's chain is small,
    # to exercise it directly rather than relying on world size.
    result = check_cheatability(world, fr.placement, logic, seed=0, exhaustive_limit=1)
    assert result.exhaustive is False
    assert result.uncheatable is True
    assert result.subsets_checked > 0


def test_removing_a_single_chain_claim_is_the_first_thing_checked():
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)
    result = check_cheatability(world, fr.placement, logic, seed=0)
    # Every single-item-removal subset is a proper subset of a 4-item chain,
    # so an exhaustive run must have covered strictly more than just those.
    assert result.subsets_checked >= 4
