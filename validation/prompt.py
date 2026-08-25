"""The fixed instruction text handed to a solver-under-test, plus the facts
for one task. No prose, no narrative framing -- a restatement, in plain
English, of the exact fixed-point rule `seedbed.solver.solve` runs in code.
The model gets nothing the solver doesn't: it is being asked to execute the
same procedure the oracle executes, over the same inputs.
"""

from __future__ import annotations

import json
from typing import Any, Dict

INSTRUCTIONS = """You are given a placement of claims into slots, and must determine which \
claims are recoverable and how.

DEFINITIONS
- Each SLOT has an id and an author (an actor). A slot may carry zero or \
more claims (see "claims_carried_here").
- Each CLAIM has an id, a "target" flag, a "min_role" (the minimum \
authority role its author must hold), an optional "eligible_authors" list \
(if present, only those actor ids may carry this claim), and \
"support_alternatives": a list of alternative prerequisite sets. Satisfying \
ANY ONE alternative is enough to establish the claim. An alternative that \
is an empty list needs no prerequisites at all (a root claim).
- ACCESS_EDGES is a directed graph over slot ids. Edge [a, b] means \
information present at slot a can reach slot b. Reachability is transitive \
(a path of edges, not just one hop) but NOT symmetric -- do not assume \
[a, b] implies [b, a].
- Role authority, low to high, is given by "role_order_low_to_high".

RECOVERY RULE (apply until no more claims can be added -- a fixed point)
A claim C is KNOWN if all of the following hold:
  1. C is carried by some slot S (i.e. C appears in S's "claims_carried_here").
  2. S's author may legally carry C: the author's role rank is >= C's \
"min_role" rank, AND (if C has "eligible_authors") the author is in that list.
  3. At least one of C's "support_alternatives" is fully satisfied: every \
prerequisite claim P in that alternative is itself KNOWN, and P's carrying \
slot can reach S via one or more ACCESS_EDGES (a path, possibly through \
slots that carry no claim at all -- those slots still exist as pass-through \
points in the graph even though they don't appear in "claims_carried_here" \
for any claim).
A claim with an empty-list alternative needs no prerequisite path check for \
that alternative (rule 3 is trivially satisfied by that alternative).

A claim NOT carried by any slot (absent from every "claims_carried_here") \
can never become known.

TASK
Determine whether the claim with "target": true is KNOWN under this rule. \
If it is, report the full set of claim ids that are load-bearing for it: \
the target itself, plus every claim actually used (directly or \
transitively, via the specific support alternative that got credited) to \
establish it. Do not include claims that happen to be KNOWN but play no \
part in supporting the target.

OUTPUT
Respond with ONLY a single JSON object, no other text, of the exact shape:
{"target_known": <true|false>, "chain": [<claim ids load-bearing for the \
target, or [] if target_known is false>]}
"""


def build_prompt(facts: Dict[str, Any]) -> str:
    return INSTRUCTIONS + "\nFACTS:\n" + json.dumps(facts, indent=2, sort_keys=True)
