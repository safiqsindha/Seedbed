from seedbed.toyworld import build_world


def test_world_shape():
    world = build_world()
    assert len(world.actors) == 8
    assert len(world.slots) == 40
    assert len(world.claims) == 6


def test_chain_vs_distractor_split():
    world = build_world()
    assert world.chain_claim_ids() == frozenset({"c1", "c2", "c3", "c4"})
    assert world.distractor_claim_ids() == frozenset({"c5", "c6"})


def test_exactly_one_target():
    world = build_world()
    targets = [c for c in world.claims.values() if c.target]
    assert len(targets) == 1
    assert targets[0].id == "c4"
