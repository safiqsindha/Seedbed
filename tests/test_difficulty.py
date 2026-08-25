from seedbed.access import TIERS
from seedbed.difficulty import DEFAULT_WEIGHTS, score
from seedbed.fill import assumed_fill
from seedbed.solver import solve
from seedbed.toyworld import build_world

SEEDS = range(60)


def test_stricter_logic_never_makes_a_fixed_placement_easier():
    """Monotonicity, stated over the axis where it is actually meaningful.

    Scoring one *fixed* placement under each tier isolates the effect of
    access-logic strictness. Comparing independently generated placements
    instead conflates two variables -- different tiers pick different
    support routes entirely -- and is checked separately below.
    """
    world = build_world()
    compared = strictly_harder = 0

    for seed in SEEDS:
        fr = assumed_fill(world, TIERS["easy"], seed=seed)
        totals = {}
        for name, logic in TIERS.items():
            if not solve(world, fr.placement, logic).solved:
                break
            totals[name] = score(world, fr.placement, logic).total
        else:
            compared += 1
            assert totals["hard"] >= totals["standard"] >= totals["easy"], (seed, totals)
            if totals["hard"] > totals["easy"]:
                strictly_harder += 1

    assert compared >= 30, f"weak sample: only {compared} placements solvable across all tiers"
    assert strictly_harder > compared // 2, (
        f"only {strictly_harder}/{compared} placements got strictly harder easy->hard; "
        "the tiers are not separating"
    )


def test_hop_count_is_the_structurally_monotonic_component():
    """Removing edges can only lengthen or sever the shortest path, so
    hop_count must never fall as strictness rises. This is the guarantee the
    total inherits."""
    world = build_world()
    for seed in SEEDS:
        fr = assumed_fill(world, TIERS["easy"], seed=seed)
        hops = {}
        for name, logic in TIERS.items():
            if not solve(world, fr.placement, logic).solved:
                break
            hops[name] = score(world, fr.placement, logic).hop_count
        else:
            assert hops["hard"] >= hops["standard"] >= hops["easy"], (seed, hops)


def test_distractor_density_is_not_a_constant():
    """It was 1.0 on every seed once, which made it dead weight in the
    score while looking like a real signal."""
    world = build_world()
    values = set()
    for seed in SEEDS:
        for logic in TIERS.values():
            fr = assumed_fill(world, logic, seed=seed)
            values.add(round(score(world, fr.placement, logic).distractor_density, 6))
    assert len(values) > 1, f"distractor_density never varied: {values}"


def test_decoy_lens_is_tier_invariant():
    """Decoy proximity is judged under a fixed permissive lens, because a
    reader does not know the access rules -- inferring them is the task."""
    world = build_world()
    fr = assumed_fill(world, TIERS["easy"], seed=0)
    densities = {
        name: score(world, fr.placement, logic).distractor_density
        for name, logic in TIERS.items()
        if solve(world, fr.placement, logic).solved
    }
    assert len(set(densities.values())) == 1, densities


def test_weights_are_tunable():
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)

    default = score(world, fr.placement, logic)
    hop_only = score(
        world,
        fr.placement,
        logic,
        weights={
            "hop_count": 1.0,
            "authority_reversal": 0.0,
            "distractor_density": 0.0,
            "low_salience_fraction": 0.0,
        },
    )
    assert hop_only.total == hop_only.hop_count
    assert default.weights == DEFAULT_WEIGHTS
    assert hop_only.weights != DEFAULT_WEIGHTS


def test_difficulty_is_measured_over_the_live_route_only():
    """Scoring the potential chain would let unreachable decoys inflate it."""
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)
    route = solve(world, fr.placement, logic).live_route
    assert route < frozenset(fr.placement), "some claims should be stranded off-route"
    carriers = {fr.placement[c] for c in route}
    assert all(world.slots[s].salience in {"low", "normal", "high"} for s in carriers)
