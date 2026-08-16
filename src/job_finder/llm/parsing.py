"""Shared LLM-response parsing utilities.

Both the drafter and the haiku triage layer ask Anthropic for structured JSON
and tolerate stray prose / markdown fences around it. This module is the
single source of truth for that pull-out logic so the regex and error shape
stay consistent across callers.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Greedy-match the outermost {...} block. Tolerates leading/trailing prose.
_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def extract_json_object(text: str, *, what: str = "LLM response") -> dict[str, Any]:
    """Find and parse the first JSON object in `text`.

    Raises `ValueError` with a 200-char snippet if no object is present or
    the object isn't valid JSON. `what` is a noun phrase used in the error
    message ("drafter response", "haiku triage batch", etc.).
    """
    m = _OBJECT_RE.search(text)
    if not m:
        raise ValueError(f"no JSON object in {what}: {text[:200]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON in {what} ({e}): {text[:200]!r}") from e
