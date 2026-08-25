"""Guards that the three logic tiers are actually three distinct tiers.

`hard` used to be nearly inert: it agreed with `standard` on 89 of 100
seeds, so the engine nominally offered three difficulty settings and
effectively offered two.
"""

from seedbed.access import TIERS
from seedbed.fill import assumed_fill
from seedbed.toyworld import build_world

SEEDS = range(50)


def _placement(world, tier_name, seed):
    return tuple(sorted(assumed_fill(world, TIERS[tier_name], seed=seed).placement.items()))


def test_each_tier_pair_diverges_on_most_seeds():
    world = build_world()
    agreements = {"easy_standard": 0, "standard_hard": 0, "easy_hard": 0}

    for seed in SEEDS:
        easy = _placement(world, "easy", seed)
        standard = _placement(world, "standard", seed)
        hard = _placement(world, "hard", seed)
        agreements["easy_standard"] += easy == standard
        agreements["standard_hard"] += standard == hard
        agreements["easy_hard"] += easy == hard

    n = len(SEEDS)
    for pair, same in agreements.items():
        assert same < n // 2, (
            f"{pair} produced identical placements on {same}/{n} seeds; "
            "these tiers are not meaningfully distinct"
        )


def test_strictness_is_ordered_by_edge_count():
    from seedbed.access import build_adjacency

    world = build_world()
    edges = {
        name: sum(len(v) for v in build_adjacency(world, logic).values())
        for name, logic in TIERS.items()
    }
    assert edges["hard"] < edges["standard"] < edges["easy"], edges


def test_every_tier_still_fills_every_seed():
    """Separation must not be bought by making `hard` unsatisfiable."""
    world = build_world()
    for seed in SEEDS:
        for name in TIERS:
            fr = assumed_fill(world, TIERS[name], seed=seed)
            assert fr.placement, f"tier {name} failed to fill seed {seed}"
