import random

import pytest

from seedbed.access import TIERS
from seedbed.cheat import check_cheatability
from seedbed.fill import (
    SearchBudgetExceeded,
    UnsolvableWorldError,
    assumed_fill,
)
from seedbed.model import ROOT, Claim, requires
from seedbed.solver import solve
from seedbed.toyworld import build_world

SEEDS = range(20)


def test_same_seed_is_byte_identical():
    world = build_world()
    logic = TIERS["standard"]
    a = assumed_fill(world, logic, seed=42)
    b = assumed_fill(world, logic, seed=42)
    assert a.placement == b.placement
    assert a.order == b.order
    assert [(r.claim_id, r.candidates, r.chosen, r.reason, r.alternative) for r in a.rolls] == [
        (r.claim_id, r.candidates, r.chosen, r.reason, r.alternative) for r in b.rolls
    ]


def test_different_seeds_can_diverge():
    world = build_world()
    logic = TIERS["standard"]
    placements = {tuple(sorted(assumed_fill(world, logic, seed=s).placement.items())) for s in SEEDS}
    assert len(placements) > 1, "seeded fill should explore more than one placement across 20 seeds"


def test_every_claim_gets_its_own_legally_carriable_slot():
    world = build_world()
    for tier in TIERS.values():
        fr = assumed_fill(world, tier, seed=0)
        assert set(fr.placement) == set(world.claims)
        assert len(set(fr.placement.values())) == len(fr.placement), "no two claims share a slot"
        # Requirement 1: every placement respects access logic, distractors
        # included -- not just the ones on the recovery path.
        for cid, slot_id in fr.placement.items():
            assert tier.can_carry(world, world.slots[slot_id], world.claims[cid])


def _reference_placement(world, logic, cap=400_000):
    """Independent backtracking enumerator sharing no pruning logic with
    fill.py -- only the public solve()/check_cheatability contract."""
    cids = sorted(world.claims)
    carriable = {
        c: [s for s in sorted(world.slots) if logic.can_carry(world, world.slots[s], world.claims[c])]
        for c in cids
    }
    placement, used, budget = {}, set(), [0]

    def bt(i):
        if budget[0] > cap:
            raise TimeoutError
        if i == len(cids):
            budget[0] += 1
            return (
                solve(world, placement, logic).solved
                and check_cheatability(world, placement, logic, seed=0).uncheatable
            )
        for slot_id in carriable[cids[i]]:
            if slot_id in used:
                continue
            placement[cids[i]] = slot_id
            used.add(slot_id)
            if bt(i + 1):
                return True
            del placement[cids[i]]
            used.discard(slot_id)
        return False

    return dict(placement) if bt(0) else None


def test_fill_is_complete_no_false_negatives():
    """Regression guard for the engine's worst historical bug.

    The first revision placed greedily with no retraction, and raised
    UnsolvableWorldError on ~35% of worlds that were in fact fillable. The
    search must fail only when failure is real.
    """
    rng = random.Random(7)
    fillable = false_negatives = false_positives = impossible = 0

    for trial in range(25):
        world = build_world()
        keep = rng.sample(sorted(world.slots), rng.randint(12, 18))
        world.slots = {k: world.slots[k] for k in keep}
        logic = TIERS[rng.choice(["easy", "standard", "hard"])]
        try:
            reference = _reference_placement(world, logic)
        except TimeoutError:
            continue

        if reference is None:
            impossible += 1
            try:
                assumed_fill(world, logic, seed=trial)
                false_positives += 1
            except (UnsolvableWorldError, SearchBudgetExceeded):
                pass
            continue

        fillable += 1
        try:
            assumed_fill(world, logic, seed=trial)
        except UnsolvableWorldError:
            false_negatives += 1
        except SearchBudgetExceeded:
            pass

    assert fillable >= 10, f"weak sample: only {fillable} fillable worlds"
    assert false_negatives == 0, f"{false_negatives}/{fillable} fillable worlds wrongly rejected"
    assert false_positives == 0, f"{false_positives}/{impossible} impossible worlds wrongly accepted"


def test_pathological_claim_cycle_fails_loudly():
    world = build_world()
    world.claims["c_bad"] = Claim("c_bad", "impossible", support=requires("c_bad"))
    with pytest.raises(UnsolvableWorldError):
        assumed_fill(world, TIERS["standard"], seed=0)


def test_pathological_unreachable_authority_fails_loudly():
    world = build_world()
    # Only frank is exec-ranked; strip his slots so an exec-only claim has
    # nowhere legal to go.
    world.slots = {sid: s for sid, s in world.slots.items() if s.author != "frank"}
    with pytest.raises(UnsolvableWorldError):
        assumed_fill(world, TIERS["standard"], seed=0)


def test_pathological_no_eligible_author_fails_loudly():
    world = build_world()
    world.claims["c_bad"] = Claim(
        "c_bad", "nobody can write this", support=ROOT, eligible_authors=frozenset({"nonexistent"})
    )
    with pytest.raises(UnsolvableWorldError):
        assumed_fill(world, TIERS["standard"], seed=0)


def test_budget_exhaustion_is_not_reported_as_impossibility():
    """"Don't know" and "proven impossible" must stay distinguishable --
    conflating them is how an engine quietly declares a solvable world dead.
    """
    world = build_world()
    with pytest.raises(SearchBudgetExceeded):
        assumed_fill(world, TIERS["hard"], seed=0, node_budget=1)
    assert not issubclass(SearchBudgetExceeded, UnsolvableWorldError)
    assert not issubclass(UnsolvableWorldError, SearchBudgetExceeded)


def test_search_reports_how_many_solutions_it_compared():
    """Difficulty maximization is a bounded best-of-N, and the bound has to
    be visible rather than passed off as a global optimum."""
    world = build_world()
    fr = assumed_fill(world, TIERS["standard"], seed=0, solution_limit=4)
    assert 0 < fr.solutions_compared <= 4
