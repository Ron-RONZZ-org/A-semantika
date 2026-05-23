"""Tests for _triple_search.py resolution and search orchestration helpers.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _setup_nodes_and_predicates(node_svc, pred_svc) -> None:
    """Create test data: nodes + predicates."""
    # Use hex-only UUIDs with distinct prefixes to resolve uniquely
    node_svc.create({"node_id": "a1000000-0000-0000-0000-000000000001", "etikedoj": {"eo": "Hundo"}})
    node_svc.create({"node_id": "a2000000-0000-0000-0000-000000000002", "etikedoj": {"eo": "Kato"}})
    node_svc.create({"node_id": "a3000000-0000-0000-0000-000000000003", "etikedoj": {"eo": "Mamulo"}})
    # rdf:type is seeded by DEFAULT_PREDICATES in storage.py — no need to create
    pred_svc.create({"predicate_id": "wdt:P1082", "etikedoj": {"eo": "logxantaro", "en": "population"}})


@pytest.fixture
def _with_triples(triple_svc) -> None:
    """Add some triples for search testing."""
    triple_svc.add(
        subject_uuid="a1000000-0000-0000-0000-000000000001",
        predicate_id="rdf:type",
        object_value="a3000000-0000-0000-0000-000000000003",
        object_type="uri",
    )
    triple_svc.add(
        subject_uuid="a2000000-0000-0000-0000-000000000002",
        predicate_id="rdf:type",
        object_value="a3000000-0000-0000-0000-000000000003",
        object_type="uri",
    )


# ── resolve_subjects ──────────────────────────────────────────────────────────


class TestResolveSubjects:
    """Tests for resolve_subjects()."""

    def test_uuid_prefix(self, node_svc) -> None:
        """UUID prefix should resolve to the matching node."""
        from A_semantika._triple_search import resolve_subjects

        uuids = resolve_subjects(node_svc, "a1000000-")
        assert uuids == ["a1000000-0000-0000-0000-000000000001"]

    def test_ambiguous_uuid_prefix_returns_empty(self, node_svc) -> None:
        """Ambiguous UUID prefix should fall through to label search."""
        from A_semantika._triple_search import resolve_subjects

        # "a1" matches both a1000000-... and a2000000-... but is too short
        # (2 chars, min 8). Falls straight to label search which also finds
        # nothing → empty.
        uuids = resolve_subjects(node_svc, "a1")
        assert uuids == []

    def test_label_search_fallback(self, node_svc) -> None:
        """Non-UUID text should fall back to FTS5 label search."""
        from A_semantika._triple_search import resolve_subjects

        # "Hundo" is 5 chars — too short for UUID prefix (min 8) AND
        # contains non-hex chars (H, u, n, d, o) — so goes straight to label search
        uuids = resolve_subjects(node_svc, "Hundo")
        assert len(uuids) >= 1
        assert "a1000000-0000-0000-0000-000000000001" in uuids

    def test_no_match_returns_empty(self, node_svc) -> None:
        """No matching nodes should return empty list."""
        from A_semantika._triple_search import resolve_subjects

        uuids = resolve_subjects(node_svc, "Neniu")
        assert uuids == []

    def test_empty_input(self, node_svc) -> None:
        """Empty input should return empty list."""
        from A_semantika._triple_search import resolve_subjects

        assert resolve_subjects(node_svc, "") == []
        assert resolve_subjects(node_svc, "   ") == []


# ── resolve_predicates ────────────────────────────────────────────────────────


class TestResolvePredicates:
    """Tests for resolve_predicates()."""

    def test_exact_id(self, pred_svc) -> None:
        """Exact predicate_id match should return it directly."""
        from A_semantika._triple_search import resolve_predicates

        ids = resolve_predicates(pred_svc, "rdf:type")
        assert ids == ["rdf:type"]

    def test_partial_label_search(self, pred_svc) -> None:
        """Partial label match should find predicates via LIKE."""
        from A_semantika._triple_search import resolve_predicates

        ids = resolve_predicates(pred_svc, "tipo")
        assert "rdf:type" in ids

    def test_partial_id_search(self, pred_svc) -> None:
        """Partial ID match should find predicates via LIKE."""
        from A_semantika._triple_search import resolve_predicates

        ids = resolve_predicates(pred_svc, "wdt:")
        assert "wdt:P1082" in ids

    def test_no_match_returns_empty(self, pred_svc) -> None:
        """No matching predicates should return empty list."""
        from A_semantika._triple_search import resolve_predicates

        assert resolve_predicates(pred_svc, "nonexistent") == []

    def test_empty_input(self, pred_svc) -> None:
        """Empty input should return empty list."""
        from A_semantika._triple_search import resolve_predicates

        assert resolve_predicates(pred_svc, "") == []


# ── resolve_objects ───────────────────────────────────────────────────────────


class TestResolveObjects:
    """Tests for resolve_objects()."""

    def test_uuid_prefix(self, node_svc) -> None:
        """UUID prefix should resolve to node UUID."""
        from A_semantika._triple_search import resolve_objects

        values = resolve_objects(node_svc, "a3000000-")
        assert values == ["a3000000-0000-0000-0000-000000000003"]

    def test_label_search_fallback(self, node_svc) -> None:
        """Non-UUID text should fall back to FTS5 label search."""
        from A_semantika._triple_search import resolve_objects

        values = resolve_objects(node_svc, "Mamulo")
        assert len(values) >= 1
        assert "a3000000-0000-0000-0000-000000000003" in values

    def test_no_match_returns_raw_text(self, node_svc) -> None:
        """No matches should return the raw text for literal matching."""
        from A_semantika._triple_search import resolve_objects

        values = resolve_objects(node_svc, "1000000")
        assert values == ["1000000"]

    def test_empty_input(self, node_svc) -> None:
        """Empty input should return empty list."""
        from A_semantika._triple_search import resolve_objects

        assert resolve_objects(node_svc, "") == []


# ── search_triples_by_labels ──────────────────────────────────────────────────


class TestSearchTriplesByLabels:
    """Integration tests for search_triples_by_labels()."""

    def test_search_by_subject_uuid_prefix(self, node_svc, pred_svc, triple_svc, _with_triples) -> None:
        """Search by subject UUID prefix should find triples."""
        from A_semantika._triple_search import search_triples_by_labels

        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            subject="a1000000-",
        )
        assert len(results) >= 1
        assert all(r["subject_uuid"] == "a1000000-0000-0000-0000-000000000001" for r in results)

    def test_search_by_subject_label(self, node_svc, pred_svc, triple_svc, _with_triples) -> None:
        """Search by subject label should find triples."""
        from A_semantika._triple_search import search_triples_by_labels

        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            subject="Hundo",
        )
        assert len(results) >= 1
        assert all(r["subject_uuid"] == "a1000000-0000-0000-0000-000000000001" for r in results)

    def test_search_by_predicate_label(self, node_svc, pred_svc, triple_svc, _with_triples) -> None:
        """Search by predicate label should find triples."""
        from A_semantika._triple_search import search_triples_by_labels

        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            predicate="tipo",
        )
        assert len(results) >= 2

    def test_search_by_predicate_exact_id(self, node_svc, pred_svc, triple_svc, _with_triples) -> None:
        """Search by exact predicate ID should find triples."""
        from A_semantika._triple_search import search_triples_by_labels

        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            predicate="rdf:type",
        )
        assert len(results) >= 2

    def test_search_combined_subject_and_predicate(self, node_svc, pred_svc, triple_svc, _with_triples) -> None:
        """Combined subject + predicate should narrow results."""
        from A_semantika._triple_search import search_triples_by_labels

        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            subject="Kato",
            predicate="rdf:type",
        )
        assert len(results) >= 1
        assert all(r["subject_uuid"] == "a2000000-0000-0000-0000-000000000002" for r in results)

    def test_no_match_returns_empty(self, node_svc, pred_svc, triple_svc) -> None:
        """No matching triples should return empty list."""
        from A_semantika._triple_search import search_triples_by_labels

        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            subject="Neniu",
        )
        assert results == []

    def test_no_filters_returns_all(self, node_svc, pred_svc, triple_svc, _with_triples) -> None:
        """No filters should return all triples (up to limit)."""
        from A_semantika._triple_search import search_triples_by_labels

        # search_triples_by_labels requires at least one filter to use the
        # search path. If none provided, it returns all.
        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            limit=50,
        )
        assert len(results) >= 2
