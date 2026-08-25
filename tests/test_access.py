from seedbed.access import TIERS, build_adjacency
from seedbed.model import Slot
from seedbed.toyworld import build_world


def test_hard_tier_has_strictly_fewer_edges_than_standard_and_easy():
    world = build_world()
    edge_counts = {}
    for name, logic in TIERS.items():
        adj = build_adjacency(world, logic)
        edge_counts[name] = sum(len(v) for v in adj.values())
    assert edge_counts["hard"] < edge_counts["standard"] < edge_counts["easy"]


def test_large_meeting_is_not_an_edge_under_hard_but_is_under_easy():
    world = build_world()
    # erin (sales) and heidi (legal): different teams, no reporting line, no
    # thread -- the *only* thing that could connect them is a shared
    # meeting. Give them one sized well above hard's cap.
    big_meeting_size = 8
    src = Slot(
        id="synthetic_src",
        author="erin",
        timestamp=1,
        channel="meeting_notes",
        audience=frozenset({"erin", "heidi"} | {f"x{i}" for i in range(big_meeting_size - 2)}),
        meeting="m_synthetic_big",
    )
    dst = Slot(
        id="synthetic_dst",
        author="heidi",
        timestamp=2,
        channel="meeting_notes",
        audience=src.audience,
        meeting="m_synthetic_big",
    )
    assert TIERS["easy"].connected(world, src, dst)
    assert not TIERS["hard"].connected(world, src, dst)


def test_same_author_always_connects_regardless_of_tier():
    world = build_world()
    a = world.slots["s01"]  # dave, t=1
    b = world.slots["s02"]  # dave, t=2
    for logic in TIERS.values():
        assert logic.connected(world, a, b)


def test_time_never_flows_backwards():
    world = build_world()
    later = world.slots["s10"]
    earlier = world.slots["s01"]
    for logic in TIERS.values():
        assert not logic.connected(world, later, earlier)
