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


def test_hard_tier_prunes_stale_edges():
    """`max_time_gap` applies even within one author -- staleness is about
    the age of the source, not about who is carrying it."""
    world = build_world()
    fresh = world.slots["s01"]  # dave, t=1
    stale = world.slots["s34"]  # dave, t=6 -- same author, gap 5
    assert TIERS["hard"].max_time_gap == 6
    assert TIERS["hard"].connected(world, fresh, stale)

    # Same author (frank), gap 9 -- so nothing *but* staleness can explain a
    # difference between the tiers here.
    src = world.slots["s07"]  # frank, t=5
    dst = world.slots["s22"]  # frank, t=14
    assert src.author == dst.author
    assert TIERS["easy"].connected(world, src, dst)
    assert not TIERS["hard"].connected(world, src, dst)


def test_hard_edges_are_a_strict_subset_of_standard():
    """Monotonic difficulty depends on strictness being nested: every edge
    `hard` admits, `standard` must admit too."""
    world = build_world()
    slots = list(world.slots.values())
    hard_edges, standard_edges = set(), set()
    for src in slots:
        for dst in slots:
            if TIERS["hard"].connected(world, src, dst):
                hard_edges.add((src.id, dst.id))
            if TIERS["standard"].connected(world, src, dst):
                standard_edges.add((src.id, dst.id))
    assert hard_edges < standard_edges
