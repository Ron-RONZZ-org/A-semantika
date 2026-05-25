"""Shared helper functions for NodeService.

Extracted from _node_service.py to keep that file under 500 lines.
Contains label/definition text extraction and FTS5 keyword handling.
"""
from __future__ import annotations

import json


# FTS5 keywords that need to be lowercased (not stripped) when they
# appear in user search queries, so they are treated as content terms
# rather than FTS5 operators.
FTS5_KEYWORDS = {"AND", "OR", "NOT", "NEAR", "COLUMN"}


def extract_label_text(etikedoj: str | dict) -> str:
    """Denormalize etikedoj JSON into a flat searchable string.

    Concatenates all label values separated by spaces.
    """
    try:
        labels = json.loads(etikedoj) if isinstance(etikedoj, str) else etikedoj
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(labels, dict):
        return ""
    return " ".join(str(v) for v in labels.values() if v)


def extract_difin_text(difinoj: str | dict) -> str:
    """Denormalize difinoj JSON into a flat searchable string."""
    try:
        defns = json.loads(difinoj) if isinstance(difinoj, str) else difinoj
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(defns, dict):
        return ""
    return " ".join(str(v) for v in defns.values() if v)
