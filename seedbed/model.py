"""Core data model: actors, claims, slots, and the world they live in.

Terminology mirrors the randomizer prior art (see docs/PRIOR_ART_REPORT.md):
Slot <-> Location, Claim <-> Item, the access graph <-> the world graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional

# Role authority ranking, low to high. A slot's author can only carry a
# claim whose min_role they meet or exceed -- the "hookshot behind a
# hookshot door" analogue for authority rather than graph distance.
ROLE_RANK: Dict[str, int] = {"ic": 0, "manager": 1, "exec": 2}


@dataclass(frozen=True)
class Actor:
    id: str
    role: str  # key into ROLE_RANK
    team: str


@dataclass(frozen=True)
class Claim:
    """An atomic fact to be placed into some slot.

    requires: prerequisite claim ids that must already be inferable before
        this claim can be legally carried (a claim-level dependency DAG,
        independent of the slot access graph).
    target: True for the claim(s) that constitute the thing a solver is
        trying to prove. The transitive closure of `requires` back from
        every target claim is the "chain"; everything else is a distractor.
    min_role: minimum authority role required to author a slot carrying
        this claim.
    """

    id: str
    label: str
    requires: FrozenSet[str] = frozenset()
    target: bool = False
    min_role: str = "ic"
    # Empty = no restriction. Non-empty = only these actors may originate
    # this claim (e.g. only the two people actually in the room for a
    # vendor negotiation) -- a second, independently pluggable axis of
    # access logic alongside min_role and graph reachability.
    eligible_authors: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class Slot:
    """An artifact placeholder: never rendered as prose, just a carrier."""

    id: str
    author: str  # Actor id
    timestamp: int
    channel: str  # e.g. "email", "chat", "doc", "meeting_notes"
    audience: FrozenSet[str] = frozenset()  # Actor ids who can read this slot
    thread: Optional[str] = None
    meeting: Optional[str] = None
    salience: str = "normal"  # "low" | "normal" | "high"


@dataclass
class World:
    actors: Dict[str, Actor]
    slots: Dict[str, Slot]
    reports_to: Dict[str, str]  # actor id -> manager actor id
    claims: Dict[str, Claim] = field(default_factory=dict)

    def chain_claim_ids(self) -> FrozenSet[str]:
        """Transitive closure of `requires` back from every target claim,
        including the targets themselves."""
        chain: set[str] = set()
        stack = [c.id for c in self.claims.values() if c.target]
        while stack:
            cid = stack.pop()
            if cid in chain:
                continue
            chain.add(cid)
            stack.extend(self.claims[cid].requires)
        return frozenset(chain)

    def distractor_claim_ids(self) -> FrozenSet[str]:
        return frozenset(self.claims) - self.chain_claim_ids()
