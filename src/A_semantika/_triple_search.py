"""Triple search helper — resolves partial labels to UUIDs/IDs then queries.

Keeps TripleService pure (only accepts resolved UUIDs/predicate_ids).
Resolution logic is isolated here for reuse by both serci and the
interactive modifi/forigi picker.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from A import tr_multi, warning as _warning
from A_semantika._constants import is_numeric, looks_like_uuid_prefix
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._triple_ranking import rank_triples_by_bm25

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService


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
    if looks_like_uuid_prefix(text):
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
    if not looks_like_uuid_prefix(text):
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
        or is_numeric(text.strip())
        or len(text.strip().split()) > 1
    )
    if not _is_obvious_literal:
        _warning(
            f"No node found for '{text[:60]}' — searching as literal value"
        )
    return ([], [text])  # literal value for LIKE match


# ── Combined search orchestration ─────────────────────────────────────────────


def _build_search_clause_any_field(
    search_term: str,
    node_svc,
    pred_svc,
) -> tuple[str, list]:
    """Build a unified WHERE clause for any-field search.
    
    Resolves search_term to UUIDs/IDs across subjects, predicates, and objects,
    then constructs a single WHERE clause that ORs across all fields.
    
    Args:
        search_term: The user's search input.
        node_svc: NodeService instance for node resolution.
        pred_svc: PredicateService instance for predicate resolution.
    
    Returns:
        (where_clause, params): SQL WHERE string and parameter values.
    """
    subject_uuids = resolve_subjects(node_svc, search_term)
    predicate_ids = resolve_predicates(pred_svc, search_term)
    object_uuids, object_literals = resolve_objects(node_svc, search_term)
    
    field_clauses = []
    params = []
    
    # Subject matches: subject_uuid IN (?, ?, ...)
    if subject_uuids:
        placeholders = ",".join("?" * len(subject_uuids))
        field_clauses.append(f"subject_uuid IN ({placeholders})")
        params.extend(subject_uuids)
    
    # Predicate matches: predicate_id IN (?, ?, ...)
    if predicate_ids:
        placeholders = ",".join("?" * len(predicate_ids))
        field_clauses.append(f"predicate_id IN ({placeholders})")
        params.extend(predicate_ids)
    
    # Object URI matches: object_value IN (?, ?, ...)
    if object_uuids:
        placeholders = ",".join("?" * len(object_uuids))
        field_clauses.append(f"object_value IN ({placeholders})")
        params.extend(object_uuids)
    
    # Object literal partial matches: object_value LIKE ... OR object_value LIKE ...
    if object_literals:
        like_parts = []
        for val in object_literals:
            escaped = val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like_parts.append("object_value LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")
        field_clauses.append(f"({' OR '.join(like_parts)})")
    
    # Join all field clauses with OR
    where_clause = " OR ".join(f"({c})" for c in field_clauses) if field_clauses else "1=1"
    
    return where_clause, params


def _build_relevance_order_by(search_term: str, node_svc, pred_svc) -> str | None:
    """Build a SQL ORDER BY CASE expression that prioritizes exact matches.
    
    Resolves search_term to exact node_ids and constructs a CASE expression
    that sorts results with exact matches first.
    
    Args:
        search_term: The user's search input.
        node_svc: NodeService instance.
        pred_svc: PredicateService instance.
    
    Returns:
        SQL ORDER BY clause string (e.g., "CASE WHEN ... END, subject_uuid, predicate_id")
        or None if no exact matches are found (caller should use default sort).
    
    **Security note:** UUIDs are escaped to prevent SQL injection.
    """
    # Resolve to exact matches
    exact_subjects = resolve_subjects(node_svc, search_term)
    exact_predicates = resolve_predicates(pred_svc, search_term)
    exact_objects, _ = resolve_objects(node_svc, search_term)
    
    all_exact = exact_subjects + exact_predicates + exact_objects
    
    if not all_exact:
        return None  # No exact matches; use default sort
    
    # Build CASE expression: exact object matches (priority 0), then subjects (priority 100+), then predicates (priority 200+)
    case_parts = []
    for i, uuid_id in enumerate(all_exact):
        # Escape single quotes for SQL string literals
        safe_id = uuid_id.replace("'", "''")
        
        # Object exact match (highest priority)
        case_parts.append(f"WHEN object_value = '{safe_id}' THEN {i}")
        # Subject exact match (medium priority)
        case_parts.append(f"WHEN subject_uuid = '{safe_id}' THEN {i + 100}")
        # Predicate exact match (low priority)
        case_parts.append(f"WHEN predicate_id = '{safe_id}' THEN {i + 200}")
    
    case_expr = "CASE " + " ".join(case_parts) + " ELSE 999 END"
    return f"{case_expr}, subject_uuid, predicate_id"


def search_triples_any_field(
    triple_svc: TripleService,
    node_svc: NodeService,
    pred_svc: PredicateService,
    search_term: str,
    limit: int = 100,
    dato_de: str | None = None,
    dato_gis: str | None = None,
) -> list[dict]:
    """Search triples where *search_term* matches subject, predicate, OR object.

    Constructs a unified WHERE clause that ORs across all fields,
    prioritizing exact matches via relevance ordering.

    Literal object values use LIKE-based partial matching so that
    searching for e.g. ``"Lament"`` finds arcs with ``"A Mathematician's Lament"``.

    Args:
        triple_svc: TripleService instance.
        node_svc: NodeService instance.
        pred_svc: PredicateService instance.
        search_term: The text to search across all fields.
        limit: Maximum results to return.
        dato_de: ISO 8601 start datetime (inclusive) for ``kreita_je`` filter.
        dato_gis: ISO 8601 end datetime (inclusive) for ``kreita_je`` filter.

    Returns:
        List of unique matching triple dicts, ranked by relevance.
    """
    if not search_term or not search_term.strip():
        return []

    # Build unified WHERE clause
    where_clause, params = _build_search_clause_any_field(search_term, node_svc, pred_svc)
    
    # Build relevance ORDER BY clause
    order_by = _build_relevance_order_by(search_term, node_svc, pred_svc)
    
    # Execute single query with unified WHERE
    results = triple_svc.search_triples(
        where_clause, params, order_by=order_by, limit=limit,
        dato_de=dato_de, dato_gis=dato_gis,
    )
    return rank_triples_by_bm25(results, node_svc, search_term)


def _build_search_clause_by_labels(
    triple_svc,
    node_svc,
    pred_svc,
    subject: str | None = None,
    predicate: str | None = None,
    object: str | None = None,  # noqa: A002
) -> tuple[str, list]:
    """Build a unified WHERE clause for label-based search.
    
    Each parameter is independently resolved (OR within each parameter,
    AND across parameters). Empty resolution for any parameter means
    'no restriction' (not 'no results').
    
    Args:
        triple_svc: TripleService instance (not used, but kept for consistency).
        node_svc: NodeService instance.
        pred_svc: PredicateService instance.
        subject: Subject label or UUID prefix.
        predicate: Predicate label or exact ID.
        object: Object label, UUID prefix, or literal value.
    
    Returns:
        (where_clause, params): SQL WHERE string and parameter values.
    """
    # Resolve each parameter independently
    subject_uuids = resolve_subjects(node_svc, subject) if subject else None
    predicate_ids = resolve_predicates(pred_svc, predicate) if predicate else None
    object_uuids: list[str] | None = None
    object_literals: list[str] | None = None
    if object:
        object_uuids, object_literals = resolve_objects(node_svc, object)
    
    clauses: list[str] = []
    params: list = []
    
    # Subject constraint
    if subject_uuids is not None:
        if not subject_uuids:
            # Empty resolution means no results
            return "0=1", []  # Impossible WHERE clause
        placeholders = ",".join("?" * len(subject_uuids))
        clauses.append(f"subject_uuid IN ({placeholders})")
        params.extend(subject_uuids)
    
    # Predicate constraint
    if predicate_ids is not None:
        if not predicate_ids:
            # Empty resolution means no results
            return "0=1", []  # Impossible WHERE clause
        placeholders = ",".join("?" * len(predicate_ids))
        clauses.append(f"predicate_id IN ({placeholders})")
        params.extend(predicate_ids)
    
    # Object constraint (URI or literal)
    object_clauses = []
    if object_uuids is not None:
        if not object_uuids and not object_literals:
            # Empty resolution means no results
            return "0=1", []
        if object_uuids:
            placeholders = ",".join("?" * len(object_uuids))
            object_clauses.append(f"object_value IN ({placeholders})")
            params.extend(object_uuids)
    
    if object_literals is not None:
        if object_literals:
            like_parts = []
            for val in object_literals:
                escaped = val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                like_parts.append("object_value LIKE ? ESCAPE '\\'")
                params.append(f"%{escaped}%")
            object_clauses.append(f"({' OR '.join(like_parts)})")
    
    if object_clauses:
        clauses.append(f"({' OR '.join(object_clauses)})")
    
    # Join all clauses with AND
    where_clause = " AND ".join(clauses) if clauses else "1=1"
    
    return where_clause, params


def search_triples_by_labels(
    triple_svc: TripleService,
    node_svc: NodeService,
    pred_svc: PredicateService,
    subject: str | None = None,
    predicate: str | None = None,
    object: str | None = None,  # noqa: A002
    limit: int = 100,
    dato_de: str | None = None,
    dato_gis: str | None = None,
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
        dato_de: ISO 8601 start datetime (inclusive) for ``kreita_je`` filter.
        dato_gis: ISO 8601 end datetime (inclusive) for ``kreita_je`` filter.

    Returns:
        List of matching triple dicts.
    """
    # Build unified WHERE clause
    where_clause, params = _build_search_clause_by_labels(
        triple_svc, node_svc, pred_svc, subject, predicate, object
    )
    
    # Execute single query with unified WHERE
    results = triple_svc.search_triples(
        where_clause, params, limit=limit,
        dato_de=dato_de, dato_gis=dato_gis,
    )
    return rank_triples_by_bm25(results, node_svc, subject, predicate, object)
