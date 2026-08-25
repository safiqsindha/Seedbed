"""Render a placement as structured facts for a solver-under-test.

No prose, no narrative -- only what `seedbed.solver.solve` itself consults:
which slot carries which claim, who may author it, and how slots connect.
Everything the difficulty scorer needs beyond that (labels, salience,
timestamps, channel, thread/meeting ids) is withheld, because the reference
solver never looks at it either once the access graph is built -- it works
from the adjacency list, not the raw slot metadata that produced it.

This is the one deliberate asymmetry worth naming: the solver is handed the
adjacency graph pre-built (`build_adjacency` runs once, outside the loop
under test). Rendering that graph as facts rather than the raw metadata
means the model isn't asked to re-derive connectivity rules -- it is asked
to do the fixed-point recovery, which is what `difficulty` actually scores
(hop count, authority reversals, distractor density, low-salience carrier
fraction all presuppose the graph is known, not that it must be inferred).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from seedbed.access import AccessLogic, build_adjacency
from seedbed.model import ROLE_RANK, World

ROLE_ORDER = sorted(ROLE_RANK, key=ROLE_RANK.__getitem__)


def render_facts(
    world: World,
    placement: Mapping[str, Optional[str]],
    logic: AccessLogic,
    *,
    seed: int,
    world_name: str,
) -> Dict[str, Any]:
    """`placement` maps claim id -> slot id, or -> None for a claim held
    back from this run (the spurious-success ablation drops one this way --
    identical to how `cheat.check_cheatability` tests a subset)."""
    adj = build_adjacency(world, logic)
    slot_claims: Dict[str, List[str]] = {sid: [] for sid in world.slots}
    for cid, sid in placement.items():
        if sid is not None:
            slot_claims[sid].append(cid)

    return {
        "world": world_name,
        "tier": logic.name,
        "seed": seed,
        "role_order_low_to_high": ROLE_ORDER,
        "actors": [
            {"id": a.id, "role": a.role}
            for a in sorted(world.actors.values(), key=lambda a: a.id)
        ],
        "claims": [
            {
                "id": c.id,
                "target": c.target,
                "min_role": c.min_role,
                "eligible_authors": sorted(c.eligible_authors) or None,
                # Each inner list is one sufficient alternative; an empty
                # list means "needs nothing" (a root claim). Any ONE
                # alternative being satisfied is enough.
                "support_alternatives": [sorted(alt) for alt in c.support],
            }
            for c in sorted(world.claims.values(), key=lambda c: c.id)
        ],
        "slots": [
            {
                "id": sid,
                "author": world.slots[sid].author,
                "claims_carried_here": sorted(slot_claims[sid]),
            }
            for sid in sorted(world.slots)
        ],
        # Directed: edge [a, b] means information present at slot a can
        # reach slot b. Not necessarily symmetric.
        "access_edges": [[src, dst] for src in sorted(adj) for dst in adj[src]],
    }
