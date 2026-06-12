"""Shared constants and heuristic helpers for A-semantika modules.

Extracted from _node_helpers.py, _predicate_service.py, and _triple_search.py
to keep individual modules self-contained and under 500 lines while avoiding
duplication of constant definitions and shared helper functions.
"""

from __future__ import annotations

import re


# FTS5 keywords that need to be lowercased (not stripped) when they
# appear in user search queries, so they are treated as content terms
# rather than FTS5 operators.
FTS5_KEYWORDS: frozenset[str] = frozenset({
    "AND",
    "OR",
    "NOT",
    "NEAR",
    "COLUMN",
})


# ── Heuristic helpers for text classification ──────────────────────────

_UUID_PREFIX_RE = re.compile(r"^[0-9a-fA-F\-]+$")


def looks_like_uuid_prefix(text: str) -> bool:
    """Check if text looks like a UUID prefix.

    A text looks like a UUID prefix if it is:
    - Between 8 and 16 characters long (UUID prefix typical length)
    - Contains only hex digits [0-9a-fA-F] and hyphens

    Short alphanumeric strings that are not hex (like 'Hundo' at 5 chars,
    'tipo' at 4 chars) won't match because they're too short or contain
    non-hex characters, preventing pointless DB lookups.
    """
    return 8 <= len(text) <= 16 and bool(_UUID_PREFIX_RE.match(text))


def is_numeric(text: str) -> bool:
    """Check if text represents a numeric value (int or float)."""
    try:
        float(text)
        return True
    except (ValueError, TypeError):
        return False
