"""Pluggable access logic: the analogue of RequirementsMet()/canFill() from
the randomizer prior art.

An AccessLogic decides two things:
  - connected(world, src, dst): can knowledge present at slot `src` reach
    slot `dst` (same thread / meeting / team / reporting line, and never
    backwards in time)?
  - can_carry(world, slot, claim): may `slot`'s author legally originate
    `claim` at all, independent of reachability (the authority check)?

Three tiers (EASY/STANDARD/HARD) are provided as different strictness
settings of the same predicate -- not hardcoded special cases -- so a new
tier is just a new set of flags, and a caller can supply an entirely custom
AccessLogic if the flags aren't expressive enough.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .model import ROLE_RANK, Claim, Slot, World


@dataclass(frozen=True)
class AccessLogic:
    name: str
    # connected() strictness -- four independent, non-overlapping knobs:
    allow_same_team_shortcut: bool  # same team alone counts, with no thread/meeting/reporting
    require_audience_overlap: bool  # dst's author must appear in src's audience
    cross_team_requires_reporting_or_meeting: bool  # a shared thread isn't enough across teams
    max_meeting_size_for_edge: Optional[int]  # None = any size; a large all-hands isn't a real tie
    # None = knowledge keeps indefinitely. A number caps how stale a source
    # may be: past that gap nobody is expected to still be carrying it, not
    # even its own author. This is the knob that most sharply separates the
    # tiers, because it prunes long-range edges the other flags leave intact.
    max_time_gap: Optional[int]

    def connected(self, world: World, src: Slot, dst: Slot) -> bool:
        if src.id == dst.id:
            return False
        if dst.timestamp < src.timestamp:
            return False  # knowledge never flows backwards in time
        if self.max_time_gap is not None and dst.timestamp - src.timestamp > self.max_time_gap:
            return False  # the source is too stale to still be in play

        author_a = world.actors[src.author]
        author_b = world.actors[dst.author]

        same_author = src.author == dst.author
        if same_author:
            return True  # an actor trivially carries their own earlier knowledge forward

        same_thread = src.thread is not None and src.thread == dst.thread
        same_meeting = (
            src.meeting is not None
            and src.meeting == dst.meeting
            and (self.max_meeting_size_for_edge is None or len(src.audience) <= self.max_meeting_size_for_edge)
        )
        same_team = author_a.team == author_b.team
        reporting = (
            world.reports_to.get(src.author) == dst.author
            or world.reports_to.get(dst.author) == src.author
        )

        if same_team:
            edge = same_thread or same_meeting or reporting or self.allow_same_team_shortcut
        else:
            edge = reporting or same_meeting or (same_thread and not self.cross_team_requires_reporting_or_meeting)

        if not edge:
            return False
        if self.require_audience_overlap and author_b.id not in src.audience:
            return False
        return True

    def can_carry(self, world: World, slot: Slot, claim: Claim) -> bool:
        author = world.actors[slot.author]
        if ROLE_RANK[author.role] < ROLE_RANK[claim.min_role]:
            return False
        if claim.eligible_authors and author.id not in claim.eligible_authors:
            return False
        return True


EASY = AccessLogic(
    name="easy",
    allow_same_team_shortcut=True,
    require_audience_overlap=False,
    cross_team_requires_reporting_or_meeting=False,
    max_meeting_size_for_edge=None,
    max_time_gap=None,
)
STANDARD = AccessLogic(
    name="standard",
    allow_same_team_shortcut=True,
    require_audience_overlap=True,
    cross_team_requires_reporting_or_meeting=False,
    max_meeting_size_for_edge=None,
    max_time_gap=None,
)
HARD = AccessLogic(
    name="hard",
    allow_same_team_shortcut=False,
    require_audience_overlap=True,
    cross_team_requires_reporting_or_meeting=True,
    max_meeting_size_for_edge=2,
    # Scaled to the toy world's 1..18 timeline: roughly "older than a third
    # of the project's history is stale". Chosen for that rationale rather
    # than for the number that separates the tiers best -- callers with a
    # real timeline should set their own. Without it `hard` was nearly
    # inert, agreeing with `standard` on 89 of 100 seeds.
    max_time_gap=6,
)

TIERS: Dict[str, AccessLogic] = {t.name: t for t in (EASY, STANDARD, HARD)}


def build_adjacency(world: World, logic: AccessLogic) -> Dict[str, List[str]]:
    """Directed adjacency list over every slot in the world (the full graph
    -- most slots carry no claim and exist purely as connective tissue,
    exactly like item-less locations in a randomizer world graph)."""
    slots = list(world.slots.values())
    adj: Dict[str, List[str]] = {s.id: [] for s in slots}
    for src in slots:
        for dst in slots:
            if logic.connected(world, src, dst):
                adj[src.id].append(dst.id)
    return adj


def bfs_reachable(adj: Dict[str, List[str]], src: str) -> Set[str]:
    """All slot ids reachable from `src` (BFS, mirrors GetReachableLocations)."""
    seen = {src}
    queue = [src]
    while queue:
        cur = queue.pop(0)
        for nxt in adj.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def shortest_path(adj: Dict[str, List[str]], src: str, dst: str) -> List[str] | None:
    """Shortest slot-id path src->dst (BFS), or None if unreachable."""
    if src == dst:
        return [src]
    seen = {src}
    queue = [[src]]
    while queue:
        path = queue.pop(0)
        cur = path[-1]
        for nxt in adj.get(cur, ()):
            if nxt in seen:
                continue
            new_path = path + [nxt]
            if nxt == dst:
                return new_path
            seen.add(nxt)
            queue.append(new_path)
    return None


def all_simple_paths(
    adj: Dict[str, List[str]], src: str, dst: str, cap: int = 200
) -> List[List[str]]:
    """All non-self-intersecting paths src->dst (recursive DFS, mirrors
    PathsToRegion). Capped at `cap` results to bound cost on dense graphs;
    callers that hit the cap should treat branching-factor stats as a
    lower bound and say so."""
    results: List[List[str]] = []

    def _dfs(cur: str, visited: Set[str], path: List[str]) -> None:
        if len(results) >= cap:
            return
        if cur == dst:
            results.append(list(path))
            return
        for nxt in adj.get(cur, ()):
            if nxt in visited:
                continue
            visited.add(nxt)
            path.append(nxt)
            _dfs(nxt, visited, path)
            path.pop()
            visited.discard(nxt)

    _dfs(src, {src}, [src])
    return results
