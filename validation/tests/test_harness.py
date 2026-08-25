"""Sanity checks for the validation harness itself -- not the model study,
which needs live agent calls. These confirm the harness's own logic (facts
rendering, oracle, scoring, the ablation invariant) is correct before any
tokens are spent on model calls.
"""

from __future__ import annotations

from seedbed.access import TIERS
from seedbed.api import build_world, generate

from validation.facts import render_facts
from validation.oracle import compute_oracle
from validation.scoring import score_answer


def _seed(world_name="toy", tier="standard", seed=0):
    world = build_world(world_name)
    logic = TIERS[tier]
    result = generate(world, tier=logic, seed=seed)
    return world, logic, result


def test_oracle_agrees_with_generate():
    world, logic, result = _seed()
    oracle = compute_oracle(world, result.placement, logic)
    assert oracle.solved is True
    assert oracle.live_route == result.live_route
    assert oracle.target_id in oracle.live_route


def test_facts_omit_labels_and_salience():
    world, logic, result = _seed()
    facts = render_facts(world, result.placement, logic, seed=0, world_name="toy")
    blob = str(facts)
    # No claim label text or salience level should leak into the facts --
    # the solver-under-test gets exactly what solve() consults, no more.
    assert "vendor_contract_signed" not in blob  # a claim label
    assert '"salience"' not in blob
    assert '"timestamp"' not in blob


def test_facts_placement_round_trips():
    world, logic, result = _seed()
    facts = render_facts(world, result.placement, logic, seed=0, world_name="toy")
    reconstructed = {}
    for slot in facts["slots"]:
        for cid in slot["claims_carried_here"]:
            reconstructed[cid] = slot["id"]
    assert reconstructed == dict(result.placement)


def test_scoring_perfect_answer():
    world, logic, result = _seed()
    oracle = compute_oracle(world, result.placement, logic)
    answer = {"target_known": True, "chain": sorted(oracle.live_route)}
    score = score_answer(oracle, answer)
    assert score.binary_correct is True
    assert score.f1 == 1.0
    assert score.precision == 1.0
    assert score.recall == 1.0


def test_scoring_wrong_boolean_on_solved_oracle():
    world, logic, result = _seed()
    oracle = compute_oracle(world, result.placement, logic)
    assert oracle.solved
    answer = {"target_known": False, "chain": []}
    score = score_answer(oracle, answer)
    assert score.binary_correct is False
    assert score.f1 == 0.0  # a real live route exists; the model claimed none


def test_scoring_f1_is_none_only_when_oracle_unsolved():
    world, logic, result = _seed()
    oracle = compute_oracle(world, result.placement, logic)
    non_target = sorted(oracle.live_route - {oracle.target_id})
    ablated = dict(result.placement)
    ablated[non_target[0]] = None
    unsolved_oracle = compute_oracle(world, ablated, logic)
    assert unsolved_oracle.solved is False
    score = score_answer(unsolved_oracle, {"target_known": False, "chain": []})
    assert score.binary_correct is True
    assert score.f1 is None


def test_scoring_partial_chain():
    world, logic, result = _seed()
    oracle = compute_oracle(world, result.placement, logic)
    true_route = sorted(oracle.live_route)
    assert len(true_route) >= 2, "need a multi-claim route for a partial-credit test"
    partial = true_route[:-1] + ["not_a_real_claim"]
    answer = {"target_known": True, "chain": partial}
    score = score_answer(oracle, answer)
    assert score.binary_correct is True
    assert 0.0 < score.f1 < 1.0


def test_ablating_a_live_route_claim_breaks_solvability():
    """This is the structural guarantee the spurious-success check leans
    on: seedbed's own uncheatability property means dropping any single
    live-route claim must make the target unrecoverable."""
    world, logic, result = _seed()
    oracle = compute_oracle(world, result.placement, logic)
    non_target = sorted(oracle.live_route - {oracle.target_id})
    assert non_target
    dropped = non_target[0]
    ablated = dict(result.placement)
    ablated[dropped] = None
    ablated_oracle = compute_oracle(world, ablated, logic)
    assert ablated_oracle.solved is False
