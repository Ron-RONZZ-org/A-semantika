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
) -> list[str]:
    """Resolve text to node IDs via UUID prefix, FTS5 label search, or node_id prefix.

    Shared helper used by both resolve_subjects() and resolve_objects()
    — encapsulates the common UUID-prefix-then-FTS5-then-node_id-prefix
    resolution pattern.

    Resolution order:
    1. If text looks like a UUID prefix, try resolve_node_id_prefix()
    2. Fall back to NodeService.search() via FTS5 label search
    3. If still no match, try resolve_node_id_prefix() for non-UUID text
       (covers short human-readable node IDs like "H_GL")
    4. Return empty list if no matches

    Returns:
        List of matching node IDs, or empty list if no match.
        For ambiguous prefixes this includes ALL matching node IDs
        (not just the first one).
    """
    if not text or not text.strip():
        return []

    # Step 1: Try UUID prefix resolution
    if _looks_like_uuid_prefix(text):
        try:
            node = node_svc.resolve_node_id_prefix(text)
            if node:
                return [node["node_id"]]
        except AmbiguousUUIDError as e:
            _warning(tr_multi(
                "Ambigua prefikso '{t}' — pluraj nodoj kongruas",
                "Ambiguous prefix '{t}' — multiple nodes match",
                "Préfixe ambigu '{t}' — plusieurs nœuds correspondent",
            ).format(t=text))
            # Include ALL matching nodes so the caller can search for any
            # of them — more useful than silently returning empty.
            return [m["node_id"] for m in e.matches]
        except ValueError:
            pass  # Not found — fall through to label search

    # Step 2: FTS5 label search
    results = node_svc.search(text, limit=50)
    if results:
        return [r["node_id"] for r in results]

    # Step 3: Fallback — try node_id prefix resolution for non-UUID text.
    # This covers short human-readable node IDs like "H_GL" (4 chars,
    # non-hex) that don't look like UUID prefixes but are valid node_id
    # prefixes.  FTS5 doesn't index node_id, so label search won't match.
    if not _looks_like_uuid_prefix(text):
        try:
            node = node_svc.resolve_node_id_prefix(text)
            if node:
                return [node["node_id"]]
        except AmbiguousUUIDError as e:
            _warning(tr_multi(
                "Ambigua prefikso '{t}' — pluraj nodoj kongruas",
                "Ambiguous prefix '{t}' — multiple nodes match",
                "Préfixe ambigu '{t}' — plusieurs nœuds correspondent",
            ).format(t=text))
            return [m["node_id"] for m in e.matches]
        except ValueError:
            pass

    return []


def resolve_subjects(node_svc: NodeService, text: str) -> list[str]:
    """Resolve subject text to a list of node UUIDs.

    Delegates to :func:`_resolve_node_by_label` for the common
    UUID-prefix-then-FTS5 pattern. Ambiguous prefixes return ALL
    matching node IDs, not just the first one.
    """
    return _resolve_node_by_label(node_svc, text)


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


def resolve_objects(node_svc: NodeService, text: str) -> tuple[list[str], list[str]]:
    """Resolve object text to (node_uuids, literal_values).

    Returns separate lists for node UUIDs (URI objects, exact match)
    and literal values (string/int/float objects, LIKE match).

    Resolution order:
    1. Delegate to :func:`_resolve_node_by_label` (UUID prefix → FTS5)
    2. If still no matches, return the raw text as a literal value
       match candidate (for LIKE-based partial matching).

    Returns:
        Tuple of (node_uuids, literal_values):
        - node_uuids: Resolved node UUIDs for exact URI matching, or
          empty list if no node matched.
        - literal_values: Raw text as literal value for LIKE matching,
          or empty list if node(s) were found.
    """
    if not text or not text.strip():
        return ([], [])

    # Step 1: Try UUID prefix resolution → FTS5 label search
    node_ids = _resolve_node_by_label(node_svc, text)
    if node_ids:
        return (node_ids, [])  # node UUIDs for exact match

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
    return ([], [text])  # literal value for LIKE match


# ── Combined search orchestration ─────────────────────────────────────────────


def search_triples_any_field(
    triple_svc: TripleService,
    node_svc: NodeService,
    pred_svc: PredicateService,
    search_term: str,
    limit: int = 100,
) -> list[dict]:
    """Search triples where *search_term* matches subject, predicate, OR object.

    Resolution is done independently per field, then triples are queried
    separately for each non-empty field resolution and merged with
    deduplication.  This gives true OR semantics across fields, unlike
    :func:`search_triples_by_labels` which ANDs across fields.

    Literal object values use LIKE-based partial matching so that
    searching for e.g. ``"Lament"`` finds arcs with ``"A Mathematician's Lament"``.

    Args:
        triple_svc: TripleService instance.
        node_svc: NodeService instance.
        pred_svc: PredicateService instance.
        search_term: The text to search across all fields.
        limit: Maximum results to return.

    Returns:
        List of unique matching triple dicts.
    """
    if not search_term or not search_term.strip():
        return []

    # Resolve each field independently
    subject_uuids = resolve_subjects(node_svc, search_term)
    predicate_ids = resolve_predicates(pred_svc, search_term)
    object_uuids, object_literals = resolve_objects(node_svc, search_term)

    seen: set[tuple[str, str, str, str]] = set()
    results: list[dict] = []

    # Helper: query one field and deduplicate
    def _query_and_merge(**field_params: list[str] | None) -> None:
        has_values = any(
            v is not None and len(v) > 0
            for v in field_params.values()
        )
        if not has_values:
            return
        for triple in triple_svc.search_triples(**field_params, limit=limit):
            key = (
                triple["subject_uuid"],
                triple["predicate_id"],
                triple["object_value"],
                triple["object_type"],
            )
            if key not in seen:
                seen.add(key)
                results.append(triple)

    if subject_uuids:
        _query_and_merge(subject_uuids=subject_uuids)
    if predicate_ids:
        _query_and_merge(predicate_ids=predicate_ids)
    if object_uuids:
        _query_and_merge(object_values=object_uuids)
    if object_literals:
        _query_and_merge(object_values_like=object_literals)

    return results


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

    Literal object values use LIKE-based partial matching so that
    searching for e.g. ``"Lament"`` finds ``"A Mathematician's Lament"``.

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
    object_uuids: list[str] | None = None
    object_literals: list[str] | None = None
    if object:
        object_uuids, object_literals = resolve_objects(node_svc, object)

    # Delegate to TripleService.search_triples()
    return triple_svc.search_triples(
        subject_uuids=subject_uuids,
        predicate_ids=predicate_ids,
        object_values=object_uuids,
        object_values_like=object_literals,
        limit=limit,
    )
