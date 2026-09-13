"""Canonical service names.

Staff type the service by hand, so the same job arrives spelled several ways —
"FULL WASH", "FULLWASH", "FULL" and "full" are all one service. Charting the raw
text would show them as separate services and mislead the reader, so everything
is folded into a canonical name on read. The original text is never rewritten:
if a rule here turns out wrong, fixing the rule fixes every past entry too.

Rules are tried in order and the first match wins, so the specific ones
("UNDERCOAT") must come before the general ones ("UNDER").
"""

NOT_SPECIFIED = "Not specified"
OTHER = "Other"

# (canonical name, substrings that identify it)
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("PUC", ("PUC",)),
    ("Full Wash", ("FULL",)),
    ("Quick Wash", ("QUICK", "Q/W")),
    ("Undercoat", ("UNDERCOAT",)),
    ("Under Wash", ("UNDERWASH", "UNDEWASH", "UNDER+", "UNDER WASH")),
    ("Body Wash", ("BODY",)),
    ("Chain Wash", ("CHAIN",)),
    ("Test Work", ("TEST",)),
    ("Engine Room", ("ENGINE", "ENGNIE", "ENGIN")),
    ("Wash + Oil", ("OIL",)),
    ("Wash + Lube", ("LUBE",)),
    ("Grease", ("GREASE", "GRASE", "GRESE")),
    ("Vacuum", ("VACCUM", "VACUUM")),
    ("Interior", ("INTERIOR", "MAT")),
    ("Wash", ("WASH", "WATER")),
]


def canonical_service(raw: str | None) -> str:
    """Fold one free-text service name into a canonical one."""
    text = (raw or "").strip().upper()
    if not text:
        return NOT_SPECIFIED
    for name, needles in _RULES:
        if any(needle in text for needle in needles):
            return name
    return OTHER
