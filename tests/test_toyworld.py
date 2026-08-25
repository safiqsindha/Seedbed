from seedbed.toyworld import build_world


def test_world_shape():
    world = build_world()
    assert len(world.actors) == 8
    assert len(world.slots) == 40
    assert len(world.claims) == 7


def test_chain_vs_distractor_split():
    world = build_world()
    # c2b is *potentially* load-bearing: it is one of c3's two supports.
    assert world.chain_claim_ids() == frozenset({"c1", "c2", "c2b", "c3", "c4"})
    assert world.distractor_claim_ids() == frozenset({"c5", "c6"})


def test_target_has_two_independent_support_routes():
    """Without a disjunction somewhere in the chain there is no shortcut to
    look for, and the cheatability check has nothing to measure."""
    world = build_world()
    assert len(world.claims["c3"].support) == 2
    assert world.claims["c3"].prerequisite_ids == frozenset({"c2", "c2b"})


def test_exactly_one_target():
    world = build_world()
    targets = [c for c in world.claims.values() if c.target]
    assert len(targets) == 1
    assert targets[0].id == "c4"
