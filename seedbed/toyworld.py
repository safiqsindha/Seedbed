"""Hand-authored toy world: 8 actors, 40 slots, 7 claims.

No prose, no real org data -- slots are structs. Structure (who reports to
whom, which threads/meetings exist, which slots are candidates for which
claim) is authored by hand; nothing here is randomly generated. The seeded
RNG only ever chooses *among* these hand-authored candidates at fill time.

Claim chain (target = c4):
    c1 (vendor_contract_signed, sales)
      -> c2 (budget_reallocated, manager+)     \\
                                                >-> c3 (timeline_slipped, eng)
    c2b (staffing_frozen, manager+)            /       -> c4 [TARGET, exec]

c3 is supported by EITHER c2 OR c2b -- two independent routes to the same
conclusion. This is the point of the disjunction: the filler must ensure
exactly one of them is actually live (the other's carrier has to land
somewhere that cannot reach c3's slot), which makes the losing route a
genuine near-miss decoy rather than inert filler. It is also what gives the
cheatability check something real to detect: were both routes live, dropping
either one would still leave the target recoverable.

Distractors (never load-bearing for the target):
    c5 (vendor_contract_amended) -- branches off c1, dead-ends
    c6 (office_lease_renewed) -- unrelated, no dependents
"""

from __future__ import annotations

from .model import ROOT, Actor, Claim, Slot, World, either, requires

ACTORS = {
    a.id: a
    for a in [
        Actor("alice", "ic", "eng"),
        Actor("bob", "ic", "eng"),
        Actor("carol", "manager", "eng"),
        Actor("dave", "ic", "sales"),
        Actor("erin", "manager", "sales"),
        Actor("frank", "exec", "exec"),
        Actor("grace", "ic", "legal"),
        Actor("heidi", "manager", "legal"),
    ]
}

REPORTS_TO = {
    "alice": "carol",
    "bob": "carol",
    "dave": "erin",
    "grace": "heidi",
    "carol": "frank",
    "erin": "frank",
    "heidi": "frank",
}

CLAIMS = {
    c.id: c
    for c in [
        Claim("c1", "vendor_contract_signed", support=ROOT, min_role="ic",
              eligible_authors=frozenset({"dave", "erin"})),
        Claim("c2", "budget_reallocated", support=requires("c1"), min_role="manager",
              eligible_authors=frozenset({"carol", "erin", "frank"})),
        Claim("c2b", "staffing_frozen", support=ROOT, min_role="manager",
              eligible_authors=frozenset({"carol", "erin", "frank"})),
        # Two independent routes to the same conclusion; the filler makes
        # exactly one live and strands the other.
        Claim("c3", "timeline_slipped", support=either(["c2"], ["c2b"]), min_role="ic",
              eligible_authors=frozenset({"alice", "bob", "carol"})),
        Claim("c4", "exec_briefed_on_risk", support=requires("c3"), target=True, min_role="exec"),
        Claim("c5", "vendor_contract_amended", support=requires("c1"), min_role="ic",
              eligible_authors=frozenset({"dave", "erin"})),
        Claim("c6", "office_lease_renewed", support=ROOT, min_role="ic",
              eligible_authors=frozenset({"grace", "heidi"})),
    ]
}

# (id, author, timestamp, channel, audience, thread, meeting, salience)
_SLOT_ROWS = [
    # --- sales world: c1 candidates + surrounding filler ---
    ("s01", "dave", 1, "chat", {"dave", "erin"}, "th_sales1", None, "normal"),
    ("s02", "dave", 2, "doc", {"dave", "erin"}, "th_sales1", None, "low"),
    ("s03", "erin", 2, "chat", {"dave", "erin"}, "th_sales1", None, "normal"),
    ("s04", "dave", 3, "email", {"dave", "erin", "frank"}, "th_sales2", None, "normal"),
    ("s05", "erin", 4, "email", {"dave", "erin", "frank"}, "th_sales2", None, "high"),
    # --- sales-exec sync meeting (bridges sales -> exec) ---
    ("s06", "erin", 5, "meeting_notes", {"erin", "frank"}, None, "m_sync1", "normal"),
    ("s07", "frank", 5, "meeting_notes", {"erin", "frank"}, None, "m_sync1", "normal"),
    # --- decoy branch: c5 candidates, dead-ends here ---
    ("s08", "dave", 3, "doc", {"dave", "erin"}, "th_sales1", None, "low"),
    ("s09", "erin", 6, "chat", {"dave", "erin"}, None, None, "low"),
    # --- budget review meeting (bridges sales -> eng mgmt -> exec) ---
    ("s10", "erin", 7, "meeting_notes", {"carol", "erin", "frank"}, None, "m_budget", "normal"),
    ("s11", "carol", 7, "meeting_notes", {"carol", "erin", "frank"}, None, "m_budget", "normal"),
    ("s12", "frank", 7, "meeting_notes", {"carol", "erin", "frank"}, None, "m_budget", "high"),
    # --- carol relays budget outcome forward through her own artifacts ---
    ("s13", "carol", 8, "doc", {"carol"}, "th_eng_mgmt", None, "normal"),
    ("s14", "carol", 9, "chat", {"carol", "frank"}, "th_eng_mgmt", None, "normal"),
    # --- eng standup meeting (bridges eng mgmt -> eng ICs): c3 candidates ---
    ("s15", "carol", 10, "meeting_notes", {"alice", "bob", "carol"}, None, "m_standup", "normal"),
    ("s16", "alice", 10, "meeting_notes", {"alice", "bob", "carol"}, None, "m_standup", "normal"),
    ("s17", "bob", 10, "meeting_notes", {"alice", "bob", "carol"}, None, "m_standup", "low"),
    # --- eng thread, more c3 candidates ---
    ("s18", "alice", 11, "chat", {"alice", "bob"}, "th_eng1", None, "normal"),
    ("s19", "bob", 11, "email", {"alice", "bob", "carol"}, "th_eng1", None, "normal"),
    ("s20", "alice", 12, "doc", {"alice", "bob", "carol"}, "th_eng1", None, "low"),
    # --- carol carries the eng signal back up to frank: c4 (target) candidates ---
    ("s21", "carol", 13, "chat", {"carol", "frank"}, "th_eng_mgmt", None, "normal"),
    ("s22", "frank", 14, "doc", {"carol", "frank"}, None, None, "high"),
    ("s23", "frank", 15, "email", {"carol", "erin", "frank", "heidi"}, None, None, "normal"),
    # --- all-hands meeting (bridges everyone, low-salience carrier options) ---
    (
        "s24",
        "frank",
        16,
        "meeting_notes",
        {"alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi"},
        None,
        "m_allhands",
        "low",
    ),
    (
        "s25",
        "carol",
        16,
        "meeting_notes",
        {"alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi"},
        None,
        "m_allhands",
        "low",
    ),
    # --- legal world: mostly unrelated, c6 candidates ---
    ("s26", "grace", 1, "doc", {"grace", "heidi"}, "th_legal1", None, "normal"),
    ("s27", "heidi", 2, "chat", {"grace", "heidi"}, "th_legal1", None, "low"),
    ("s28", "grace", 3, "email", {"grace", "heidi"}, "th_legal1", None, "normal"),
    ("s29", "heidi", 4, "doc", {"grace", "heidi", "frank"}, None, None, "normal"),
    ("s30", "heidi", 17, "meeting_notes", {"heidi", "frank"}, None, "m_legal1", "normal"),
    ("s31", "frank", 17, "meeting_notes", {"heidi", "frank"}, None, "m_legal1", "high"),
    # --- pure filler: noise slots that carry no claim in any seed ---
    ("s32", "alice", 1, "chat", {"alice", "bob"}, "th_eng_noise1", None, "low"),
    ("s33", "bob", 2, "chat", {"alice", "bob"}, "th_eng_noise1", None, "low"),
    ("s34", "dave", 6, "chat", {"dave"}, None, None, "low"),
    ("s35", "erin", 9, "doc", {"erin"}, None, None, "normal"),
    ("s36", "grace", 8, "chat", {"grace"}, None, None, "low"),
    ("s37", "heidi", 10, "doc", {"heidi"}, None, None, "normal"),
    ("s38", "bob", 12, "email", {"bob", "carol"}, None, None, "normal"),
    ("s39", "alice", 13, "chat", {"alice", "carol"}, None, None, "low"),
    ("s40", "frank", 18, "doc", {"frank"}, None, None, "high"),
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
    return World(actors=dict(ACTORS), slots=slots, reports_to=dict(REPORTS_TO), claims=dict(CLAIMS))
