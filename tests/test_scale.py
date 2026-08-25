"""Guards for the forward-checking that lifted the engine off toy scale.

Before it existed, a 60-slot world with an 8-claim chain found no solution
within 200k nodes even though a valid placement trivially exists: the
difficulty-maximizing order placed each claim as late in time as it could,
starving the next one, and with no lookahead the search thrashed. Every
guarantee the project reported was therefore a statement about ~40 slots.
"""

import time

import pytest

from seedbed.access import TIERS
from seedbed.fill import assumed_fill, mandatory_chain, mandatory_claims
from seedbed.model import ROOT, Actor, Claim, Slot, World, either, requires
from seedbed.solver import solve


def chain_world(n_slots: int, chain_len: int, n_actors: int = 12) -> World:
    actors = {f"a{i}": Actor(f"a{i}", "ic", f"t{i % 3}") for i in range(n_actors)}
    reports = {f"a{i}": f"a{(i + 1) % n_actors}" for i in range(n_actors)}
    slots = {
        f"s{i:03d}": Slot(
            id=f"s{i:03d}",
            author=f"a{i % n_actors}",
            timestamp=i,
            channel="chat",
            audience=frozenset(actors),
            thread=f"th{i % 4}",
            salience="low" if i % 3 else "normal",
        )
        for i in range(n_slots)
    }
    claims = {"k0": Claim("k0", "root", support=ROOT)}
    for i in range(1, chain_len):
        claims[f"k{i}"] = Claim(
            f"k{i}", f"step{i}", support=requires(f"k{i-1}"), target=(i == chain_len - 1)
        )
    return World(actors=actors, slots=slots, reports_to=reports, claims=claims)


@pytest.mark.parametrize("n_slots,chain_len", [(60, 8), (120, 14), (200, 20)])
def test_fills_worlds_well_beyond_toy_scale(n_slots, chain_len):
    world = chain_world(n_slots, chain_len)
    logic = TIERS["easy"]
    started = time.time()
    result = assumed_fill(world, logic, seed=0)
    elapsed = time.time() - started

    assert solve(world, result.placement, logic).solved
    assert len(result.placement) == len(world.claims)
    # Forward-checking should keep this in the low hundreds of nodes. The
    # old failure burned the entire 200k budget without finding anything.
    assert result.nodes_explored < 5_000, result.nodes_explored
    assert elapsed < 60, f"took {elapsed:.1f}s"


def test_long_chain_triggers_the_sampled_cheatability_path():
    """The sampling strategy the brief asked for is unreachable on the toy
    world -- its live route is 3-4 claims against a limit of 12 -- so until
    the engine could fill a longer chain, that code had never actually run
    outside a test that forced it."""
    from seedbed.cheat import check_cheatability

    world = chain_world(120, 14)
    logic = TIERS["easy"]
    result = assumed_fill(world, logic, seed=0)
    cheat = check_cheatability(world, result.placement, logic, seed=0)

    assert cheat.exhaustive is False, "a 14-claim chain should exceed the exhaustive limit"
    assert cheat.uncheatable is True
    assert cheat.subsets_checked > 0


def test_mandatory_claims_exclude_bypassable_ones():
    """The forward-check is only sound for claims on every route. A claim
    with an alternative around it may strand, so nothing follows from it."""
    actors = {"a": Actor("a", "ic", "t")}
    slots = {
        f"s{i}": Slot(f"s{i}", author="a", timestamp=i, channel="chat", audience=frozenset({"a"}))
        for i in range(4)
    }
    claims = {
        "p": Claim("p", "route one"),
        "q": Claim("q", "route two"),
        "t": Claim("t", "target", support=either(["p"], ["q"]), target=True),
    }
    world = World(actors=actors, slots=slots, reports_to={}, claims=claims)

    mandatory = mandatory_claims(world)
    assert "t" in mandatory
    assert "p" not in mandatory and "q" not in mandatory


def test_mandatory_chain_is_a_real_dependency_chain():
    world = chain_world(30, 5)
    order = [f"k{i}" for i in range(5)]
    assert mandatory_chain(world, order) == order

    from seedbed.relayworld import build_world as relay

    w = relay()
    # e3/e4 are bypassable via e4b, so they are not mandatory.
    assert mandatory_claims(w) == frozenset({"e1", "e2", "e5"})
