from __future__ import annotations

import re

# Matches ```(language)?\n...\n``` with optional surrounding whitespace
_FENCE_RE = re.compile(r"^\s*```(?:\w+)?\n(.*?)\n```\s*$", re.DOTALL)


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences if present.

    Handles:
    - ```json ... ```
    - ``` ... ```
    - Leading/trailing whitespace

    Returns original text unchanged if no fences detected.
    """
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        return m.group(1).strip()
    return stripped
