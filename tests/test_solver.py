from seedbed.access import TIERS
from seedbed.fill import assumed_fill
from seedbed.model import Actor, Claim, Slot, World, either
from seedbed.solver import solve
from seedbed.toyworld import build_world

SEEDS = range(20)


def test_every_generated_seed_is_solvable():
    world = build_world()
    for tier_name, logic in TIERS.items():
        for seed in SEEDS:
            fr = assumed_fill(world, logic, seed=seed)
            result = solve(world, fr.placement, logic)
            assert result.solved, f"seed={seed} tier={tier_name} placement={fr.placement}"
            assert result.target_ids <= result.known


def test_solver_fails_when_a_load_bearing_claim_is_missing():
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)
    route = solve(world, fr.placement, logic).live_route

    for cid in route:
        if world.claims[cid].target:
            continue
        pruned = dict(fr.placement)
        pruned[cid] = None
        assert not solve(world, pruned, logic).solved, f"{cid} was not actually load-bearing"


def test_live_route_excludes_stranded_claims():
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)
    result = solve(world, fr.placement, logic)
    assert result.live_route <= result.known
    assert result.live_route < frozenset(fr.placement)


def test_disjunction_either_route_suffices():
    actors = {"a": Actor("a", "ic", "t")}
    slots = {
        sid: Slot(sid, author="a", timestamp=i, channel="chat", audience=frozenset({"a"}))
        for i, sid in enumerate(["s1", "s2", "s3"])
    }
    claims = {
        "p": Claim("p", "route one"),
        "q": Claim("q", "route two"),
        "t": Claim("t", "target", support=either(["p"], ["q"]), target=True),
    }
    world = World(actors=actors, slots=slots, reports_to={}, claims=claims)
    logic = TIERS["easy"]

    via_p = solve(world, {"p": "s1", "q": None, "t": "s3"}, logic)
    via_q = solve(world, {"p": None, "q": "s2", "t": "s3"}, logic)
    neither = solve(world, {"p": None, "q": None, "t": "s3"}, logic)

    assert via_p.solved and via_p.live_route == frozenset({"t", "p"})
    assert via_q.solved and via_q.live_route == frozenset({"t", "q"})
    assert not neither.solved


def test_redundant_support_is_reported():
    actors = {"a": Actor("a", "ic", "t")}
    slots = {
        sid: Slot(sid, author="a", timestamp=i, channel="chat", audience=frozenset({"a"}))
        for i, sid in enumerate(["s1", "s2", "s3"])
    }
    claims = {
        "p": Claim("p", "route one"),
        "q": Claim("q", "route two"),
        "t": Claim("t", "target", support=either(["p"], ["q"]), target=True),
    }
    world = World(actors=actors, slots=slots, reports_to={}, claims=claims)
    result = solve(world, {"p": "s1", "q": "s2", "t": "s3"}, TIERS["easy"])
    assert result.solved
    assert "t" in result.redundantly_supported
