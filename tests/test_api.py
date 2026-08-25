"""Guards for the public plug-in surface.

`seedbed.api` is the contract other programs depend on; the rest of the
package is internals. These tests pin the surface so a refactor cannot
quietly change what a consumer sees.
"""

import pytest

import seedbed
from seedbed import (
    GeneratedSeed,
    available_tiers,
    available_worlds,
    build_world,
    generate,
    register_world,
)
from seedbed.model import ROOT, Actor, Claim, Slot, World

WORLDS = ["toy", "relay"]


@pytest.mark.parametrize("world_name", WORLDS)
@pytest.mark.parametrize("tier", ["easy", "standard", "hard"])
def test_generate_returns_a_verified_seed(world_name, tier):
    result = generate(build_world(world_name), tier=tier, seed=5)
    assert isinstance(result, GeneratedSeed)
    assert result.solvable and result.uncheatable
    assert result.tier == tier and result.seed == 5
    assert result.live_route and result.live_route <= set(result.placement)
    assert result.stranded == frozenset(result.placement) - result.live_route
    assert result.difficulty > 0
    assert set(result.difficulty_breakdown) == {
        "hop_count",
        "authority_reversals",
        "distractor_density",
        "low_salience_fraction",
    }


@pytest.mark.parametrize("world_name", WORLDS)
def test_generate_is_deterministic(world_name):
    a = generate(build_world(world_name), seed=11)
    b = generate(build_world(world_name), seed=11)
    assert a == b


@pytest.mark.parametrize("world_name", WORLDS)
def test_recovery_chain_is_connected_end_to_end(world_name):
    """A consumer should be able to walk `recovery` as an inference chain."""
    result = generate(build_world(world_name), seed=2)
    assert result.recovery
    reached = {step.to_claim for step in result.recovery}
    supported = {step.from_claim for step in result.recovery}
    world = build_world(world_name)
    targets = world.target_ids()
    assert targets <= reached
    assert (reached | supported) == set(result.live_route)


def test_registry_accepts_a_consumer_supplied_world():
    actors = {"a": Actor("a", "ic", "t")}
    slots = {
        f"s{i}": Slot(f"s{i}", author="a", timestamp=i, channel="chat", audience=frozenset({"a"}))
        for i in range(3)
    }
    claims = {
        "p": Claim("p", "premise"),
        "t": Claim("t", "target", support=(frozenset({"p"}),), target=True),
    }
    register_world("custom_test_world", lambda: World(actors, slots, {}, claims))

    assert "custom_test_world" in available_worlds()
    result = generate(build_world("custom_test_world"), seed=0)
    assert result.solvable and result.uncheatable


def test_unknown_world_names_itself_and_the_alternatives():
    with pytest.raises(KeyError) as excinfo:
        build_world("does_not_exist")
    assert "does_not_exist" in str(excinfo.value)
    assert "toy" in str(excinfo.value)


def test_slots_for_maps_claims_to_carriers():
    world = build_world("toy")
    result = generate(world, seed=0)
    carriers = result.slots_for(world)
    assert set(carriers) == set(result.placement)
    for cid, slot in carriers.items():
        assert slot.id == result.placement[cid]


def test_spoiler_is_available_but_not_carried_by_default():
    world = build_world("toy")
    result = generate(world, seed=0)
    assert not hasattr(result, "trace")
    log = result.spoiler(world)
    assert log["seed"] == 0
    assert len(log["search"]["trace"]) > 0


def test_available_tiers_and_worlds_are_stable_names():
    assert available_tiers() == ["easy", "hard", "standard"]
    for name in WORLDS:
        assert name in available_worlds()


def test_top_level_exports_cover_world_authoring():
    for name in ("Actor", "Claim", "Slot", "World", "ROOT", "requires", "either"):
        assert hasattr(seedbed, name), name
