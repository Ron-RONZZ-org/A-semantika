"""Shared helper functions for NodeService.

Extracted from _node_service.py to keep that file under 500 lines.
Contains label/definition text extraction, FTS5 keyword handling,
and display label resolution.
"""
from __future__ import annotations

import json
from typing import Any

from A_semantika._constants import FTS5_KEYWORDS


class AmbiguousUUIDError(ValueError):
    """Raised when a UUID prefix matches multiple nodes."""
    pass


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


def get_display_label(
    resolve_fn,  # Callable[[str], dict[str, Any] | None]
    node_id_or_prefix: str,
) -> tuple[str, str]:
    """Get (display_label, language_code) for a node.

    Resolution is delegated to the provided callable (usually
    ``NodeService.resolve_node_id_prefix``).

    Returns label in eo, falling back to en, then to the first available,
    then to the node_id prefix as last resort.
    """
    node = resolve_fn(node_id_or_prefix)
    if not node:
        return (node_id_or_prefix, "")

    try:
        labels = json.loads(node["etikedoj"])
    except (json.JSONDecodeError, TypeError):
        return (node["node_id"][:16], "")

    if not isinstance(labels, dict):
        return (node["node_id"][:16], "")

    for lang in ("eo", "en"):
        val = labels.get(lang)
        if val and isinstance(val, str):
            return (val, lang)

    # Fall back to first non-empty label in any language.
    # isinstance(val, str) guard skips non-string values (e.g. null, numeric).
    for val in labels.values():
        if val and isinstance(val, str):
            return (val, "")
    return (node["node_id"][:16], "")
