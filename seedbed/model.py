"""Core data model: actors, claims, slots, and the world they live in.

Terminology mirrors the randomizer prior art (see docs/PRIOR_ART_REPORT.md):
Slot <-> Location, Claim <-> Item, the access graph <-> the world graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, Optional, Tuple

# Role authority ranking, low to high. A slot's author can only carry a
# claim whose min_role they meet or exceed -- the "hookshot behind a
# hookshot door" analogue for authority rather than graph distance.
ROLE_RANK: Dict[str, int] = {"ic": 0, "manager": 1, "exec": 2}

# A claim's support is a tuple of ALTERNATIVES; satisfying ANY ONE of them
# makes the claim inferable. Each alternative is itself a conjunctive set of
# claim ids (all of them needed). A tuple rather than a set so iteration
# order -- and therefore the spoiler log -- is deterministic.
Support = Tuple[FrozenSet[str], ...]

#: A claim that needs nothing: exactly one alternative, the empty one.
ROOT: Support = (frozenset(),)


def requires(*claim_ids: str) -> Support:
    """One conjunctive alternative: all of `claim_ids` are needed."""
    return (frozenset(claim_ids),)


def either(*alternatives: Iterable[str]) -> Support:
    """Several alternatives, any one of which suffices.

    `either(["c2"], ["c2b", "c7"])` reads: inferable from c2 alone, OR from
    c2b and c7 together. This is what makes a *shortcut* expressible -- and
    therefore what makes the cheatability check capable of failing rather
    than being true by construction.
    """
    return tuple(frozenset(alt) for alt in alternatives)


@dataclass(frozen=True)
class Actor:
    id: str
    role: str  # key into ROLE_RANK
    team: str


@dataclass(frozen=True)
class Claim:
    """An atomic fact to be placed into some slot.

    support: alternative sufficient sets of prerequisite claims (see above).
        Defaults to ROOT -- inferable on its own.
    target: True for the claim(s) a solver is trying to prove.
    min_role: minimum authority role required to author a slot carrying it.
    eligible_authors: empty = no restriction; non-empty = only these actors
        may originate this claim (e.g. only the people actually in the room).
    """

    id: str
    label: str
    support: Support = ROOT
    target: bool = False
    min_role: str = "ic"
    eligible_authors: FrozenSet[str] = frozenset()

    @property
    def prerequisite_ids(self) -> FrozenSet[str]:
        """Every claim mentioned in any alternative."""
        return frozenset().union(*self.support) if self.support else frozenset()

    @property
    def is_root(self) -> bool:
        return any(len(alt) == 0 for alt in self.support)


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

    def target_ids(self) -> FrozenSet[str]:
        return frozenset(c.id for c in self.claims.values() if c.target)

    def chain_claim_ids(self) -> FrozenSet[str]:
        """Every claim that *could* participate in supporting a target --
        the union over all alternatives, transitively.

        Note this is the *potential* chain. Which claims are actually
        load-bearing depends on the placement, and is reported per-solve by
        SolveResult.live_route; that -- not this -- is what the cheatability
        check varies.
        """
        chain: set[str] = set()
        stack = list(self.target_ids())
        while stack:
            cid = stack.pop()
            if cid in chain:
                continue
            chain.add(cid)
            stack.extend(self.claims[cid].prerequisite_ids)
        return frozenset(chain)

    def distractor_claim_ids(self) -> FrozenSet[str]:
        return frozenset(self.claims) - self.chain_claim_ids()
