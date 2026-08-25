from seedbed.access import TIERS
from seedbed.cheat import check_cheatability
from seedbed.fill import assumed_fill
from seedbed.model import Actor, Claim, Slot, World, either
from seedbed.solver import solve
from seedbed.toyworld import build_world

SEEDS = range(12)


def _two_route_world():
    """Minimal world where the target has two independent supports, both
    live. Hand-built rather than searched for, so the regression guard below
    doesn't depend on the toy world's exact geometry."""
    actors = {"a": Actor("a", "ic", "t"), "b": Actor("b", "ic", "t")}
    slots = {
        sid: Slot(sid, author="a", timestamp=i, channel="chat", audience=frozenset({"a", "b"}))
        for i, sid in enumerate(["s1", "s2", "s3"])
    }
    claims = {
        "p": Claim("p", "route one"),
        "q": Claim("q", "route two"),
        # Either p alone or q alone proves the target: a genuine shortcut.
        "t": Claim("t", "target", support=either(["p"], ["q"]), target=True),
    }
    return World(actors=actors, slots=slots, reports_to={}, claims=claims)


def test_cheatability_check_is_not_vacuous():
    """The single most important guard in this suite.

    Under the original conjunctive-only model, `uncheatable` was true by
    construction: dropping any chain claim always broke the chain, so the
    check could not fail and told you nothing. Fed 2000 deliberately absurd
    placements it never once returned False. If this test ever stops
    detecting the shortcut below, the check has silently gone vacuous again.
    """
    world = _two_route_world()
    logic = TIERS["easy"]
    placement = {"p": "s1", "q": "s2", "t": "s3"}

    assert solve(world, placement, logic).solved
    result = check_cheatability(world, placement, logic, seed=0)

    assert result.uncheatable is False, "a target with two live routes must read as cheatable"
    assert result.counterexample is not None
    assert result.redundant_support, "the redundantly supported claim should be named"
    # And the counterexample really is a shortcut: solvable on strictly less.
    shortcut = dict(placement)
    for cid in result.live_route:
        if cid not in result.counterexample:
            shortcut[cid] = None
    assert solve(world, shortcut, logic).solved


def test_every_generated_seed_is_uncheatable_exhaustively():
    world = build_world()
    for tier_name, logic in TIERS.items():
        for seed in SEEDS:
            fr = assumed_fill(world, logic, seed=seed)
            result = check_cheatability(world, fr.placement, logic, seed=seed)
            assert result.exhaustive, "toy world's live route should always be checked exhaustively"
            assert result.uncheatable, (
                f"seed={seed} tier={tier_name} placement={fr.placement} "
                f"was recoverable from a proper subset: {result.counterexample}"
            )
            assert not result.redundant_support


def test_only_the_live_route_is_varied_not_stranded_decoys():
    """Distractors are *supposed* to be droppable -- that is what makes them
    distractors -- so varying them would fail every world containing one."""
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)
    result = check_cheatability(world, fr.placement, logic, seed=0)
    stranded = set(fr.placement) - result.live_route
    assert stranded, "the toy world should strand the losing route plus its pure decoys"
    assert not (stranded & result.live_route)


def test_sampled_mode_is_flagged_rather_than_silently_assumed():
    world = build_world()
    logic = TIERS["standard"]
    fr = assumed_fill(world, logic, seed=0)
    result = check_cheatability(world, fr.placement, logic, seed=0, exhaustive_limit=1)
    assert result.exhaustive is False
    assert result.uncheatable is True
    assert result.subsets_checked > 0
