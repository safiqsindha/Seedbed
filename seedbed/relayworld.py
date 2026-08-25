"""Second hand-authored world, deliberately unlike the toy world.

The toy world was the only thing the engine had ever run on, which made
every guarantee a statement about one topology. This one differs on the
axes most likely to hide a bug:

  * a deeper chain (5 links to the target, against the toy world's 3)
  * the disjunction sits at the **target** rather than mid-chain, so the
    two routes converge at the last step instead of the middle
  * a two-level reporting hierarchy rather than a flat one
  * authority gates stacked along the chain (ic -> manager -> ic ->
    manager -> exec) instead of concentrated at the end
  * threads that span teams, so `hard`'s cross-team rule does real work

Chain (target = e5):
    e1 (deal_terms_agreed, sales ic)
      -> e2 (forecast_revised, manager)
        -> e3 (integration_blocked, eng ic)
          -> e4 (delivery_date_moved, manager)   \\
                                                  >-> e5 [TARGET, exec]
    e4b (escalation_filed, manager)              /

e5 is supported by EITHER e4 OR e4b. e4b hangs off e2, so the losing route
is a genuine near-miss: a real escalation that simply did not reach the
person who wrote the briefing.

Distractors: e6 (unrelated), e7 (branches off e1 and dead-ends).
"""

from __future__ import annotations

from .model import ROOT, Actor, Claim, Slot, World, either, requires

ACTORS = {
    a.id: a
    for a in [
        Actor("nina", "ic", "sales"),
        Actor("omar", "manager", "sales"),
        Actor("priya", "ic", "eng"),
        Actor("quinn", "ic", "eng"),
        Actor("rosa", "manager", "eng"),
        Actor("sam", "ic", "support"),
        Actor("tara", "manager", "support"),
        Actor("uma", "exec", "exec"),
        Actor("vic", "ic", "finance"),
        Actor("wei", "manager", "finance"),
    ]
}

REPORTS_TO = {
    "nina": "omar",
    "priya": "rosa",
    "quinn": "rosa",
    "sam": "tara",
    "vic": "wei",
    "omar": "uma",
    "rosa": "uma",
    "tara": "uma",
    "wei": "uma",
}

CLAIMS = {
    c.id: c
    for c in [
        Claim("e1", "deal_terms_agreed", support=ROOT, min_role="ic",
              eligible_authors=frozenset({"nina", "omar"})),
        Claim("e2", "forecast_revised", support=requires("e1"), min_role="manager",
              eligible_authors=frozenset({"omar", "wei"})),
        Claim("e3", "integration_blocked", support=requires("e2"), min_role="ic",
              eligible_authors=frozenset({"priya", "quinn", "rosa"})),
        Claim("e4", "delivery_date_moved", support=requires("e3"), min_role="manager",
              eligible_authors=frozenset({"rosa", "tara"})),
        Claim("e4b", "escalation_filed", support=requires("e2"), min_role="manager",
              eligible_authors=frozenset({"tara", "wei"})),
        # Two routes converge on the target.
        Claim("e5", "board_briefed", support=either(["e4"], ["e4b"]), target=True,
              min_role="exec"),
        Claim("e6", "vendor_portal_migrated", support=ROOT, min_role="ic",
              eligible_authors=frozenset({"sam", "vic"})),
        Claim("e7", "discount_approved", support=requires("e1"), min_role="ic",
              eligible_authors=frozenset({"nina", "vic"})),
    ]
}

# (id, author, timestamp, channel, audience, thread, meeting, salience)
_SLOT_ROWS = [
    # --- sales origin ---
    ("r01", "nina", 1, "chat", {"nina", "omar"}, "th_deal", None, "normal"),
    ("r02", "nina", 2, "email", {"nina", "omar", "wei"}, "th_deal", None, "normal"),
    ("r03", "omar", 3, "doc", {"nina", "omar", "wei"}, "th_deal", None, "low"),
    ("r04", "omar", 4, "chat", {"omar", "wei"}, "th_deal", None, "normal"),
    ("r05", "nina", 5, "doc", {"nina"}, None, None, "low"),
    # --- finance picks it up (cross-team thread) ---
    ("r06", "wei", 5, "email", {"omar", "wei", "vic"}, "th_forecast", None, "normal"),
    ("r07", "wei", 6, "doc", {"wei", "uma"}, "th_forecast", None, "high"),
    ("r08", "vic", 6, "chat", {"vic", "wei"}, "th_forecast", None, "low"),
    ("r09", "omar", 7, "meeting_notes", {"omar", "wei"}, None, "m_fin", "normal"),
    ("r10", "wei", 7, "meeting_notes", {"omar", "wei"}, None, "m_fin", "normal"),
    # --- eng planning meeting bridges finance -> eng ---
    ("r11", "wei", 8, "meeting_notes", {"rosa", "wei"}, None, "m_plan", "normal"),
    ("r12", "rosa", 8, "meeting_notes", {"rosa", "wei"}, None, "m_plan", "normal"),
    ("r13", "rosa", 9, "chat", {"priya", "quinn", "rosa"}, "th_eng", None, "normal"),
    # --- eng thread: e3 candidates ---
    ("r14", "priya", 10, "chat", {"priya", "quinn", "rosa"}, "th_eng", None, "normal"),
    ("r15", "quinn", 10, "doc", {"priya", "quinn", "rosa"}, "th_eng", None, "low"),
    ("r16", "priya", 11, "email", {"priya", "rosa"}, "th_eng", None, "normal"),
    ("r17", "quinn", 12, "chat", {"quinn", "rosa"}, "th_eng", None, "low"),
    ("r18", "rosa", 12, "doc", {"rosa"}, "th_eng", None, "normal"),
    # --- eng mgmt -> delivery: e4 candidates ---
    ("r19", "rosa", 13, "email", {"rosa", "tara", "uma"}, "th_delivery", None, "normal"),
    ("r20", "rosa", 14, "doc", {"rosa", "uma"}, "th_delivery", None, "high"),
    ("r21", "tara", 14, "chat", {"rosa", "tara"}, "th_delivery", None, "low"),
    ("r22", "tara", 15, "email", {"tara", "uma"}, "th_delivery", None, "normal"),
    # --- support escalation branch: e4b candidates ---
    ("r23", "tara", 9, "doc", {"sam", "tara"}, "th_escal", None, "normal"),
    ("r24", "tara", 10, "email", {"tara", "uma"}, "th_escal", None, "normal"),
    ("r25", "sam", 11, "chat", {"sam", "tara"}, "th_escal", None, "low"),
    ("r26", "wei", 11, "doc", {"wei", "tara"}, "th_escal", None, "low"),
    # --- exec surface: e5 candidates ---
    ("r27", "uma", 16, "doc", {"uma"}, None, None, "high"),
    ("r28", "uma", 17, "email", {"uma", "rosa", "tara"}, None, None, "normal"),
    ("r29", "uma", 18, "meeting_notes", {"uma", "omar", "rosa"}, None, "m_board", "high"),
    ("r30", "uma", 19, "doc", {"uma"}, None, None, "normal"),
    # --- support/other filler ---
    ("r31", "sam", 2, "chat", {"sam", "tara"}, "th_support", None, "low"),
    ("r32", "sam", 3, "doc", {"sam"}, "th_support", None, "low"),
    ("r33", "tara", 4, "email", {"sam", "tara"}, "th_support", None, "normal"),
    ("r34", "sam", 13, "chat", {"sam"}, None, None, "low"),
    ("r35", "vic", 2, "doc", {"vic", "wei"}, "th_fin_ops", None, "normal"),
    ("r36", "vic", 8, "chat", {"vic"}, None, None, "low"),
    ("r37", "vic", 14, "email", {"vic", "wei"}, None, None, "normal"),
    ("r38", "quinn", 3, "chat", {"priya", "quinn"}, "th_eng_noise", None, "low"),
    ("r39", "priya", 4, "doc", {"priya", "quinn"}, "th_eng_noise", None, "low"),
    ("r40", "rosa", 20, "doc", {"rosa"}, None, None, "normal"),
    ("r41", "omar", 16, "chat", {"omar"}, None, None, "low"),
    ("r42", "wei", 17, "doc", {"wei"}, None, None, "low"),
    ("r43", "nina", 12, "chat", {"nina", "omar"}, None, None, "low"),
    ("r44", "tara", 20, "doc", {"tara"}, None, None, "normal"),
    ("r45", "uma", 21, "chat", {"uma"}, None, None, "high"),
]


def build_world() -> World:
    slots = {}
    for sid, author, ts, channel, audience, thread, meeting, salience in _SLOT_ROWS:
        slots[sid] = Slot(
            id=sid,
            author=author,
            timestamp=ts,
            channel=channel,
            audience=frozenset(audience),
            thread=thread,
            meeting=meeting,
            salience=salience,
        )
    return World(
        actors=dict(ACTORS), slots=slots, reports_to=dict(REPORTS_TO), claims=dict(CLAIMS)
    )
