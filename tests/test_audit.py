"""Guards for the search audit trail (spec component 3: "every roll logged")."""

from seedbed.access import TIERS
from seedbed.fill import assumed_fill
from seedbed.spoiler import build_spoiler_log
from seedbed.toyworld import build_world


def test_trace_records_the_branches_that_were_undone():
    """The winning placement is not an audit trail.

    With backtracking, most of the seeded decision process lives in branches
    that were tried and rejected. Logging only survivors -- as this module
    originally did -- leaves a seed reproducible but not explicable.
    """
    world = build_world()
    fr = assumed_fill(world, TIERS["standard"], seed=0)

    kinds = {e.kind for e in fr.trace}
    assert "place" in kinds
    assert "backtrack" in kinds, "undone placements must appear in the trace"

    places = sum(1 for e in fr.trace if e.kind == "place")
    backtracks = sum(1 for e in fr.trace if e.kind == "backtrack")
    solutions = sum(1 for e in fr.trace if e.kind == "solution")

    assert places == fr.nodes_explored
    assert backtracks == fr.backtracks
    assert solutions == fr.solutions_compared
    assert len(fr.trace) > len(fr.rolls), "trace must cover more than the winning placement"


def test_every_rng_draw_is_recorded():
    """Seed plus these draws are the only nondeterministic inputs, so they
    fully explain the search's shape."""
    world = build_world()
    fr = assumed_fill(world, TIERS["standard"], seed=3)

    assert sorted(fr.rng_draws.claim_order_shuffle) == sorted(world.claims)
    assert set(fr.rng_draws.slot_rank_shuffles) == set(world.claims)
    for shuffled in fr.rng_draws.slot_rank_shuffles.values():
        assert sorted(shuffled) == sorted(world.slots)
    assert fr.rng_draws.solution_choice


def test_trace_truncation_is_flagged_never_silent():
    world = build_world()
    fr = assumed_fill(world, TIERS["standard"], seed=0, trace_limit=10)
    assert fr.trace_truncated is True
    assert len(fr.trace) == 10

    full = assumed_fill(world, TIERS["standard"], seed=0)
    assert full.trace_truncated is False


def test_trace_does_not_change_the_placement():
    """Auditing must be observation only."""
    world = build_world()
    a = assumed_fill(world, TIERS["standard"], seed=11, trace_limit=1)
    b = assumed_fill(world, TIERS["standard"], seed=11, trace_limit=10_000)
    assert a.placement == b.placement
    assert a.difficulty_total == b.difficulty_total


def test_solution_scores_expose_what_best_of_n_actually_compared():
    world = build_world()
    fr = assumed_fill(world, TIERS["standard"], seed=0)
    assert len(fr.solution_scores) == fr.solutions_compared
    assert fr.difficulty_total == max(fr.solution_scores)


def test_spoiler_log_carries_the_full_search_record():
    world = build_world()
    log = build_spoiler_log(world, TIERS["standard"], seed=0)
    search = log["search"]
    for key in ("nodes_explored", "backtracks", "solutions_compared", "rng_draws", "trace"):
        assert key in search
    assert search["trace_truncated"] is False
    assert len(search["trace"]) > len(log["rolls"])
