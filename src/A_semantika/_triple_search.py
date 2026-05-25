"""Triple search helper — resolves partial labels to UUIDs/IDs then queries.

Keeps TripleService pure (only accepts resolved UUIDs/predicate_ids).
Resolution logic is isolated here for reuse by both serci and the
interactive modifi/forigi picker.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from A import tr_multi, warning as _warning
from A_semantika._node_service import AmbiguousUUIDError

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService


# ── Heuristic helpers ──────────────────────────────────────────────────────────

_UUID_PREFIX_RE = re.compile(r"^[0-9a-fA-F\-]+$")


def _looks_like_uuid_prefix(text: str) -> bool:
    """Check if text looks like a UUID prefix.

    A text looks like a UUID prefix if it is:
    - Between 8 and 16 characters long (UUID prefix typical length)
    - Contains only hex digits [0-9a-fA-F] and hyphens

    Short alphanumeric strings that are not hex (like 'Hundo' at 5 chars,
    'tipo' at 4 chars) won't match because they're too short or contain
    non-hex characters, preventing pointless DB lookups.
    """
    return 8 <= len(text) <= 16 and bool(_UUID_PREFIX_RE.match(text))


def _is_numeric(text: str) -> bool:
    """Check if text represents a numeric value (int or float)."""
    try:
        float(text)
        return True
    except (ValueError, TypeError):
        return False


# ── Subject resolution ────────────────────────────────────────────────────────


def _resolve_node_by_label(
    node_svc: NodeService, text: str,
) -> tuple[list[str], bool]:
    """Resolve text to node IDs via UUID prefix or FTS5 label search.

    Shared helper used by both resolve_subjects() and resolve_objects()
    — encapsulates the common UUID-prefix-then-FTS5 resolution pattern.

    Resolution order:
    1. If text looks like a UUID prefix, try resolve_node_id_prefix()
    2. Fall back to NodeService.search() via FTS5 label search
    3. Return empty list if no matches

    Returns:
        Tuple of (node_ids, ambiguous) where:
        - node_ids: List of matching node IDs, or empty list if no match.
        - ambiguous: True if the text was a UUID prefix that matched
          multiple nodes (prevents callers from falling through to
          literal-mode fallback).
    """
    if not text or not text.strip():
        return ([], False)

    # Step 1: Try UUID prefix resolution
    if _looks_like_uuid_prefix(text):
        try:
            node = node_svc.resolve_node_id_prefix(text)
            if node:
                return ([node["node_id"]], False)
        except AmbiguousUUIDError:
            _warning(tr_multi(
                "Ambigua prefikso '{t}' — pluraj nodoj kongruas",
                "Ambiguous prefix '{t}' — multiple nodes match",
                "Préfixe ambigu '{t}' — plusieurs nœuds correspondent",
            ).format(t=text))
            return ([], True)  # Don't fall through to FTS5 — ambiguous prefix
        except ValueError:
            pass  # Not found — fall through to label search

    # Step 2: FTS5 label search
    results = node_svc.search(text, limit=50)
    if results:
        return ([r["node_id"] for r in results], False)

    return ([], False)


def resolve_subjects(node_svc: NodeService, text: str) -> list[str]:
    """Resolve subject text to a list of node UUIDs.

    Delegates to :func:`_resolve_node_by_label` for the common
    UUID-prefix-then-FTS5 pattern. Ambiguous prefixes return empty
    (no literal-mode fallback for subjects).
    """
    node_ids, _ = _resolve_node_by_label(node_svc, text)
    return node_ids


# ── Predicate resolution ──────────────────────────────────────────────────────


def resolve_predicates(pred_svc: PredicateService, text: str) -> list[str]:
    """Resolve predicate text to a list of predicate IDs.

    Resolution order:
    1. Try exact predicate_id match (O(1) index lookup)
    2. Fall back to PredicateService.search() via LIKE on all fields
    3. Return empty list if no matches
    """
    if not text or not text.strip():
        return []

    # Step 1: Exact predicate_id match
    exact = pred_svc.get_by_predicate_id(text)
    if exact:
        return [exact["predicate_id"]]

    # Step 2: LIKE search across all predicate fields
    results = pred_svc.search(text, limit=50)
    if results:
        return [r["predicate_id"] for r in results]

    return []


# ── Object resolution ─────────────────────────────────────────────────────────


def resolve_objects(node_svc: NodeService, text: str) -> list[str]:
    """Resolve object text to a list of object values.

    For URI objects, this resolves to node UUIDs.
    For literal objects, the raw text is returned as-is.

    Resolution order:
    1. Delegate to :func:`_resolve_node_by_label` (UUID prefix → FTS5)
    2. If still no matches, return the raw text as a literal match candidate
    """
    if not text or not text.strip():
        return []

    # Step 1: Try UUID prefix resolution → FTS5 label search
    resolved, ambiguous = _resolve_node_by_label(node_svc, text)
    if resolved:
        return resolved
    if ambiguous:
        return []  # Don't fall through to literal mode — ambiguous prefix

    # Step 2: Return raw text as literal value match candidate.
    # Only warn if the text looks like it could be a mistyped node identifier
    # (single word, non-numeric). Multi-word phrases, numbers, and quoted
    # strings are clearly intentional literal searches.
    _is_obvious_literal = (
        text.strip().startswith('"')
        or text.strip().startswith("'")
        or _is_numeric(text.strip())
        or len(text.strip().split()) > 1
    )
    if not _is_obvious_literal:
        _warning(
            f"No node found for '{text[:60]}' — searching as literal value"
        )
    return [text]


# ── Combined search orchestration ─────────────────────────────────────────────


def search_triples_by_labels(
    triple_svc: TripleService,
    node_svc: NodeService,
    pred_svc: PredicateService,
    subject: str | None = None,
    predicate: str | None = None,
    object: str | None = None,  # noqa: A002
    limit: int = 100,
) -> list[dict]:
    """Search triples by resolving partial labels to UUIDs/IDs.

    Each parameter is independently resolved (OR within each parameter,
    AND across parameters). Empty resolution for any parameter means
    'no restriction' (not 'no results').

    Args:
        triple_svc: TripleService instance.
        node_svc: NodeService instance.
        pred_svc: PredicateService instance.
        subject: Subject label or UUID prefix.
        predicate: Predicate label or exact ID.
        object: Object label, UUID prefix, or literal value.
        limit: Maximum results to return.

    Returns:
        List of matching triple dicts.
    """
    # Resolve each parameter independently
    subject_uuids = resolve_subjects(node_svc, subject) if subject else None
    predicate_ids = resolve_predicates(pred_svc, predicate) if predicate else None
    object_values = resolve_objects(node_svc, object) if object else None

    # Delegate to TripleService.search_triples()
    return triple_svc.search_triples(
        subject_uuids=subject_uuids,
        predicate_ids=predicate_ids,
        object_values=object_values,
        limit=limit,
    )
