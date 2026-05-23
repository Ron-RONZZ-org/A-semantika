"""Triple search helper — resolves partial labels to UUIDs/IDs then queries.

Keeps TripleService pure (only accepts resolved UUIDs/predicate_ids).
Resolution logic is isolated here for reuse by both serci and the
interactive modifi/forigi picker.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService


# ── Heuristic helpers ──────────────────────────────────────────────────────────

_UUID_PREFIX_RE = re.compile(r"^[a-zA-Z0-9\-]+$")


def _looks_like_uuid_prefix(text: str) -> bool:
    """Check if text looks like a UUID prefix (short, alphanumeric + hyphens).

    Returns True if text ≤ 12 chars and contains only ASCII alphanumeric and
    hyphens — which means it could be a UUID prefix. Longer or non-conforming
    strings are assumed to be label searches.
    """
    return len(text) <= 12 and bool(_UUID_PREFIX_RE.match(text))


# ── Subject resolution ────────────────────────────────────────────────────────


def resolve_subjects(node_svc: NodeService, text: str) -> list[str]:
    """Resolve subject text to a list of node UUIDs.

    Resolution order:
    1. If text looks like a UUID prefix, try resolve_uuid_prefix()
    2. Fall back to NodeService.search() via FTS5 label search
    3. Return empty list if no matches
    """
    if not text or not text.strip():
        return []

    # Step 1: Try UUID prefix resolution
    if _looks_like_uuid_prefix(text):
        try:
            node = node_svc.resolve_uuid_prefix(text)
            if node:
                return [node["uuid"]]
        except ValueError:
            pass  # Ambiguous or not found — fall through to label search

    # Step 2: FTS5 label search
    results = node_svc.search(text, limit=50)
    if results:
        return [r["uuid"] for r in results]

    return []


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
    1. If text looks like a UUID prefix, try resolve_uuid_prefix()
    2. Fall back to NodeService.search() via FTS5 label search
    3. If still no matches, return the raw text as a literal match candidate
    """
    if not text or not text.strip():
        return []

    # Step 1: Try UUID prefix resolution
    if _looks_like_uuid_prefix(text):
        try:
            node = node_svc.resolve_uuid_prefix(text)
            if node:
                return [node["uuid"]]
        except ValueError:
            pass  # Ambiguous or not found

    # Step 2: FTS5 label search — match node labels (for URI objects)
    results = node_svc.search(text, limit=50)
    if results:
        return [r["uuid"] for r in results]

    # Step 3: Return raw text as literal value match candidate
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
