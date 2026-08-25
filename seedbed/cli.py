from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .access import TIERS
from .api import available_worlds, build_world
from .spoiler import dumps


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="seedbed", description="Seeded evidence placement engine.")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed (default: 0)")
    parser.add_argument("--tier", choices=sorted(TIERS), default="standard", help="access-logic strictness")
    parser.add_argument(
        "--world",
        choices=available_worlds(),
        default="toy",
        help="which bundled world to place claims into (default: toy)",
    )
    parser.add_argument("--out", type=str, default=None, help="write the spoiler log JSON here instead of stdout")
    parser.add_argument(
        "--no-trace",
        action="store_true",
        help="omit the full search trace (kept by default: it is the audit trail)",
    )
    args = parser.parse_args(argv)

    world = build_world(args.world)
    logic = TIERS[args.tier]
    output = dumps(world, logic, args.seed, include_trace=not args.no_trace)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
