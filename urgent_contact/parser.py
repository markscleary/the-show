from __future__ import annotations

import re

VALID_KEYWORDS = {"APPROVE", "REJECT", "STOP", "CONTINUE"}
_PATTERN = re.compile(r"^\s*(APPROVE|REJECT|STOP|CONTINUE)\b", re.IGNORECASE)

INVALID_FORMAT_REPLY = (
    "Invalid format. Reply APPROVE, REJECT, CONTINUE, or STOP "
    "(optionally followed by your token)."
)


def parse_keyword(text: str) -> str | None:
    """Return the uppercase keyword if text starts with a valid keyword, else None."""
    m = _PATTERN.match(text)
    if m:
        return m.group(1).upper()
    return None
