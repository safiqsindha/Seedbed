"""Confirm the README's claim that `build_adjacency` is O(slots^2) and
dominates past a few hundred slots (800 slots ~220s while search explores
~630 nodes). This only profiles and reports -- it does not implement a fix.

Usage: python -m validation.profile_adjacency
"""

from __future__ import annotations

import cProfile
import pstats
import time
from io import StringIO

from seedbed.access import STANDARD, build_adjacency
from seedbed.model import Actor, Slot, World


def _synthetic_world(n_slots: int) -> World:
    """A flat single-team world sized purely to stress build_adjacency --
    not a realistic Seedbed world, just a scaling probe."""
    actor = Actor("a0", "ic", "team0")
    slots = {
        f"s{i}": Slot(id=f"s{i}", author="a0", timestamp=i, channel="chat")
        for i in range(n_slots)
    }
    return World(actors={"a0": actor}, slots=slots, reports_to={}, claims={})


def main() -> None:
    sizes = [100, 200, 400, 800]
    print(f"{'slots':>6} {'seconds':>10} {'slots^2':>12} {'sec / slots^2 (x1e6)':>22}")
    for n in sizes:
        world = _synthetic_world(n)
        t0 = time.perf_counter()
        build_adjacency(world, STANDARD)
        elapsed = time.perf_counter() - t0
        print(f"{n:6d} {elapsed:10.3f} {n * n:12d} {elapsed / (n * n) * 1e6:22.4f}")

    print("\n--- cProfile at 800 slots ---")
    world = _synthetic_world(800)
    pr = cProfile.Profile()
    pr.enable()
    build_adjacency(world, STANDARD)
    pr.disable()
    s = StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(10)
    print(s.getvalue())


if __name__ == "__main__":
    main()
