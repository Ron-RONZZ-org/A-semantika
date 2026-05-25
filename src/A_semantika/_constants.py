"""Shared constants for A-semantika modules.

Extracted from _node_helpers.py and _predicate_service.py to keep
individual modules self-contained and under 500 lines while avoiding
duplication of constant definitions.
"""

from __future__ import annotations


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
