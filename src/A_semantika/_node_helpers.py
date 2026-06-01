"""Shared helper functions for NodeService.

Extracted from _node_service.py to keep that file under 500 lines.
Contains label/definition text extraction, FTS5 keyword handling,
and display label resolution.
"""
from __future__ import annotations

import json
import unicodedata
from typing import Any

from A_semantika._constants import FTS5_KEYWORDS


class AmbiguousUUIDError(ValueError):
    """Raised when a UUID prefix matches multiple nodes.

    Attributes:
        matches: List of matching node dicts (for interactive selection).
    """
    def __init__(self, message: str, matches: list[dict] | None = None) -> None:
        super().__init__(message)
        self.matches: list[dict] = matches or []


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


def get_label_from_node(node: dict, preferred_lang: str | None = None) -> str:
    """Extract display label from a pre-resolved node dict.

    Resolution priority:
    1. ``preferred_lang`` language (if given)
    2. Default fallback ``eo → en``
    3. First non-empty label in any language
    4. ``node_id[:16]``

    Args:
        node: Pre-resolved node dict (as returned by
            ``NodeService.resolve_node_id_prefix()``).
        preferred_lang: Optional language code to try first.

    Returns:
        Display label string.
    """
    etikedoj_raw = node.get("etikedoj", "{}")
    try:
        labels = json.loads(etikedoj_raw) if isinstance(etikedoj_raw, str) else etikedoj_raw
    except (json.JSONDecodeError, TypeError):
        return truncate_uuid(node.get("node_id", ""))

    if not isinstance(labels, dict):
        return truncate_uuid(node.get("node_id", ""))

    # Try preferred language first, then default fallback
    lang_order = (preferred_lang, "eo", "en") if preferred_lang else ("eo", "en")
    for lang in lang_order:
        val = labels.get(lang)
        if val and isinstance(val, str):
            return val

    # Fall back to first non-empty label in any language.
    # isinstance(val, str) guard skips non-string values (e.g. null, numeric).
    for val in labels.values():
        if val and isinstance(val, str):
            return val
    return truncate_uuid(node.get("node_id", ""))


def get_display_label(
    resolve_fn,  # Callable[[str], dict[str, Any] | None]
    node_id_or_prefix: str,
    preferred_lang: str | None = None,
) -> tuple[str, str]:
    """Get ``(display_label, language_code)`` for a node.

    Resolution is delegated to the provided callable (usually
    ``NodeService.resolve_node_id_prefix``).  Label extraction uses
    :func:`get_label_from_node` so the ``eo → en → first`` fallback
    is consistent across all call sites.

    Args:
        resolve_fn: Callable that resolves node_id/prefix to node dict.
        node_id_or_prefix: Node ID or prefix.
        preferred_lang: Optional language code to try first.

    Returns ``(node_id_or_prefix, "")`` if the node is not found.
    """
    node = resolve_fn(node_id_or_prefix)
    if not node:
        return (node_id_or_prefix, "")
    label = get_label_from_node(node, preferred_lang=preferred_lang)
    # Detect language code from the node's etikedoj for the label
    try:
        etikedoj_raw = node.get("etikedoj", "{}")
        labels = json.loads(etikedoj_raw) if isinstance(etikedoj_raw, str) else etikedoj_raw
        if isinstance(labels, dict):
            for lang in ("eo", "en"):
                if labels.get(lang) == label:
                    return (label, lang)
            for lang, val in labels.items():
                if val == label:
                    return (label, lang)
    except (json.JSONDecodeError, TypeError):
        pass
    return (label, "")


def truncate_uuid(uuid: str, all_uuids: list[str] | None = None) -> str:
    """Truncate a UUID for display, keeping it distinguishable.

    - If ``len(uuid) < 32``: return full UUID (short IDs like ``H_GL``,
      ``DOI_10_1007_BF02`` are human-readable and should not be truncated).
    - If ``len(uuid) >= 32`` and *all_uuids* is provided: find the first
      character position where this UUID diverges from all other UUIDs
      in the set, and truncate there (minimum 8 chars).
    - If ``len(uuid) >= 32`` and no context given: truncate to 16 chars.

    Args:
        uuid: The node_id or UUID to truncate.
        all_uuids: All UUIDs appearing in the same column context
            (for computing the minimum unique prefix).

    Returns:
        Truncated display string.
    """
    if len(uuid) < 32:
        return uuid

    if all_uuids:
        others = [u for u in all_uuids if u != uuid]
        if others:
            # Find the first position where this UUID differs from at least
            # one other UUID.  We need at least 1 character past the common
            # prefix to show divergence.
            min_len = min(len(uuid), max((len(o) for o in others), default=0))
            for i in range(min_len):
                if any(o[i] != uuid[i] for o in others):
                    # Return up to and including the divergent character,
                    # but at least 8 characters.
                    return uuid[:max(i + 1, 8)]
            # All others are a prefix of this UUID (e.g. "ABC" vs "ABCDEF").
            # Show from the shortest "other" length onward.
            min_other = min((len(o) for o in others), default=len(uuid))
            return uuid[:max(min_other + 1, 8)]
        # Single UUID in set — no context to compare.
    return uuid[:16]


def sanitize_node_id(raw_id: str) -> str:
    """Strip invisible Unicode characters from a node_id.

    Removes Unicode category ``Cf`` (format chars like zero-width space
    U+200B, U+200C, U+200D, U+FEFF) and ``Cc`` (control chars) while
    preserving alphanumerics, underscores, hyphens, colons, and standard
    ASCII whitespace.

    Args:
        raw_id: Raw node ID from user input.

    Returns:
        Cleaned node ID safe for storage and lookup.
    """
    return "".join(
        ch for ch in raw_id.strip()
        if unicodedata.category(ch) not in ("Cf", "Cc")
        or ch in (" ", "\t")
    )
    return uuid[:16]
