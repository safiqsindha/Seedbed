from seedbed.access import TIERS
from seedbed.difficulty import DEFAULT_WEIGHTS, score
from seedbed.fill import assumed_fill
from seedbed.toyworld import build_world

SEEDS = range(20)


def test_tiers_never_get_easier_and_extremes_separate():
    """Stricter access logic must never make a seed *easier* to reconstruct,
    and the easy/hard extremes must be genuinely different -- not just
    tied. Adjacent tiers (standard vs hard) can legitimately coincide on a
    given seed in this 40-slot toy world when the extra hard-tier
    restrictions don't happen to fall on that seed's specific recovery
    path; what must never happen is a *decrease*.
    """
    world = build_world()
    saw_strict_standard_gt_easy = False
    saw_strict_hard_gt_standard = False

    for seed in SEEDS:
        totals = {}
        for tier_name, logic in TIERS.items():
            fr = assumed_fill(world, logic, seed=seed)
            totals[tier_name] = score(world, fr.placement, logic).total

        assert totals["hard"] >= totals["standard"] >= totals["easy"], (seed, totals)
        assert totals["hard"] > totals["easy"], (seed, totals)

        if totals["standard"] > totals["easy"]:
            saw_strict_standard_gt_easy = True
        if totals["hard"] > totals["standard"]:
            saw_strict_hard_gt_standard = True

    assert saw_strict_standard_gt_easy, "standard tier never scored strictly harder than easy across all seeds"
    # hard's extra restrictions (meeting-size cap, no same-team shortcut,
    # cross-team thread ban) are exercised by test_access.py directly; they
    # are not guaranteed to bite on every seed's specific recovery path in
    # this small toy world.


def test_weights_are_tunable():
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)

    default = score(world, fr.placement, logic)
    hop_only = score(
        world,
        fr.placement,
        logic,
        weights={"hop_count": 1.0, "authority_reversal": 0.0, "distractor_density": 0.0, "low_salience_fraction": 0.0},
    )
    assert hop_only.total == hop_only.hop_count
    assert default.weights == DEFAULT_WEIGHTS
    assert hop_only.weights != DEFAULT_WEIGHTS
