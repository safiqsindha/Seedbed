"""Guards for the recursive-DFS path enumeration (the prior art's
PathsToRegion) actually being wired into the spoiler log.

It was written, then left unreferenced -- capability that looked present
but was never exercised.
"""

from seedbed.access import TIERS, all_simple_paths, build_adjacency
from seedbed.spoiler import PATH_COUNT_CAP, build_spoiler_log
from seedbed.toyworld import build_world


def test_dfs_enumeration_is_reachable_from_the_public_spoiler_log():
    world = build_world()
    log = build_spoiler_log(world, TIERS["easy"], seed=0)
    assert log["recovery_path"], "toy world should produce a multi-edge recovery path"
    for edge in log["recovery_path"]:
        assert "distinct_simple_paths" in edge
        assert edge["distinct_simple_paths"] >= 1
        # The shortest path is always one of them.
        assert edge["distinct_simple_paths"] >= 1 + len(edge["example_alternate_paths"])


def test_capped_counts_are_reported_as_lower_bounds():
    """A capped enumeration must not read as an exact total."""
    world = build_world()
    log = build_spoiler_log(world, TIERS["easy"], seed=0)
    for edge in log["recovery_path"]:
        if edge["distinct_simple_paths"] >= PATH_COUNT_CAP:
            assert edge["distinct_simple_paths_is_lower_bound"] is True
        else:
            assert edge["distinct_simple_paths_is_lower_bound"] is False


def test_alternate_paths_are_real_paths_and_exclude_the_shortest():
    world = build_world()
    logic = TIERS["easy"]
    adj = build_adjacency(world, logic)
    log = build_spoiler_log(world, logic, seed=0)

    for edge in log["recovery_path"]:
        shortest = edge["slot_path"]
        for path in edge["example_alternate_paths"]:
            assert path != shortest
            assert path[0] == shortest[0] and path[-1] == shortest[-1]
            assert len(set(path)) == len(path), "a simple path must not revisit a slot"
            for a, b in zip(path, path[1:]):
                assert b in adj[a], f"{a}->{b} is not an edge under {logic.name}"


def test_all_simple_paths_respects_its_cap():
    world = build_world()
    adj = build_adjacency(world, TIERS["easy"])
    capped = all_simple_paths(adj, "s01", "s24", cap=3)
    assert len(capped) <= 3
