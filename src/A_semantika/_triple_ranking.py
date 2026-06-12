"""BM25 relevance ranking for triple search results.

Extracted from ``_triple_search.py`` to keep that file under 500 lines.
Provides post-query re-ranking of triple results by FTS5 BM25 score of
matched subject/object nodes.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService

logger = logging.getLogger(__name__)


# ── FTS Query Builder ─────────────────────────────────────────────────


def _build_fts_query_from_terms(*terms: str | None) -> str | None:
    """Build a single FTS5 MATCH query from multiple search terms.

    Combines all non-None terms into a single ``OR``-joined prefix query
    suitable for BM25 scoring. Returns ``None`` if no search terms provided.
    """
    safe_tokens: list[str] = []
    for term in terms:
        if not term or not term.strip():
            continue
        for word in term.strip().split():
            cleaned = "".join(c for c in word if c.isalnum() or c == "_")
            if cleaned:
                safe_tokens.append(f"{cleaned}*")
    if not safe_tokens:
        return None
    return " OR ".join(safe_tokens)


# ── BM25 Score Fetching ───────────────────────────────────────────────


def _get_bm25_scores(
    node_svc: "NodeService",
    fts_query: str,
    node_ids: list[str],
) -> dict[str, float]:
    """Query BM25 scores for a set of node IDs.

    Uses the same column weighting as ``_node_search.py:search()``:
    ``label_text (-5.0) > difin_text (-1.0) > node_id (0.0)``.

    Returns a dict mapping ``node_id → bm25_score``.  Node IDs not found
    in the FTS index get a default high score (999.0) so they sort last.
    """
    if not node_ids or not fts_query:
        return {nid: 999.0 for nid in node_ids}

    placeholders = ",".join("?" * len(node_ids))
    sql = f"""
        SELECT f.node_id, bm25(nodes_fts, 1.2, 0.75, 0.0, -5.0, -1.0) AS _rank
        FROM nodes_fts f
        WHERE nodes_fts MATCH ? AND f.node_id IN ({placeholders})
    """
    try:
        rows = node_svc.db.execute(sql, (fts_query, *node_ids))
    except Exception:
        logger.warning("BM25 scoring query failed — returning unscored results.")
        return {nid: 999.0 for nid in node_ids}

    scores = {row["node_id"]: row["_rank"] for row in rows}
    for nid in node_ids:
        scores.setdefault(nid, 999.0)
    return scores


# ── Triple Re-ranking ─────────────────────────────────────────────────


def rank_triples_by_bm25(
    triples: list[dict],
    node_svc: "NodeService",
    *search_terms: str | None,
) -> list[dict]:
    """Re-rank triples by BM25 relevance of matched subject/object nodes.

    Triples whose subject or object has a better BM25 score (lower = more
    relevant) are ranked first.  The minimum BM25 score of the two is used
    so that a strong match on either end lifts the triple.

    This is a **post-processing** step — it does not change the SQL query.
    It is only applied when there are node-type references in the results
    (URI objects), since literal objects have no FTS index.

    Args:
        triples: Result list from ``TripleService.search_triples()``.
        node_svc: NodeService instance.
        search_terms: One or more search terms to build the FTS query from.

    Returns:
        Re-ranked triple list (same objects, different order).
    """
    if not triples:
        return triples

    fts_query = _build_fts_query_from_terms(*search_terms)
    if not fts_query:
        return triples  # no meaningful search terms — keep original order

    # Collect all unique node IDs from the result set
    node_ids: set[str] = set()
    for t in triples:
        node_ids.add(t["subject_uuid"])
        if t.get("object_type") == "uri":
            node_ids.add(t["object_value"])

    if not node_ids:
        return triples  # all literals — no BM25 data available

    scores = _get_bm25_scores(node_svc, fts_query, list(node_ids))

    # Score each triple by the minimum BM25 score of its matched nodes.
    # Lower BM25 score = better match. URIs with no score default to 999.
    scored: list[tuple[float, int, dict]] = []
    for idx, t in enumerate(triples):
        subj_score = scores.get(t["subject_uuid"], 999.0)
        obj_score = (
            scores.get(t["object_value"], 999.0)
            if t.get("object_type") == "uri"
            else 999.0
        )
        min_score = min(subj_score, obj_score)
        scored.append((min_score, idx, t))

    scored.sort(key=lambda x: (x[0], x[1]))
    return [t for _, _, t in scored]
