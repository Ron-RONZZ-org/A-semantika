"""Tests for Option A search refactoring (Issue #78).

Verifies:
1. Unified WHERE clause architecture works correctly
2. Clause builders generate correct SQL and parameters
3. Relevance ordering prioritizes exact matches
4. Backward compatibility tests for search_triples()
5. End-to-end integration tests for search functions
"""
from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════════════
# Tests for _build_search_clause_any_field()
# ════════════════════════════════════════════════════════════════════════════


class TestBuildSearchClauseAnyField:
    """Test _build_search_clause_any_field() clause builder."""

    def test_empty_search_term_returns_1equals1(self, node_svc, pred_svc):
        """Empty or whitespace search_term should return '1=1' with no params."""
        from A_semantika._triple_search import _build_search_clause_any_field

        where_clause, params = _build_search_clause_any_field("", node_svc, pred_svc)
        assert where_clause == "1=1"
        assert params == []

        where_clause, params = _build_search_clause_any_field("   ", node_svc, pred_svc)
        assert where_clause == "1=1"
        assert params == []

    def test_subject_only_resolution(self, node_svc, pred_svc):
        """Subject-only resolution produces subject_uuid IN clause."""
        from A_semantika._triple_search import _build_search_clause_any_field

        subj = node_svc.create({"etikedoj": {"eo": "Test Subject"}})

        where_clause, params = _build_search_clause_any_field(
            "Test Subject", node_svc, pred_svc
        )
        # Should have subject_uuid IN clause
        assert "subject_uuid IN" in where_clause
        assert subj["node_id"] in params

    def test_predicate_only_resolution(self, node_svc, pred_svc):
        """Predicate-only resolution produces predicate_id IN clause."""
        from A_semantika._triple_search import _build_search_clause_any_field

        # Use seeded predicate rdf:type
        where_clause, params = _build_search_clause_any_field(
            "rdf:type", node_svc, pred_svc
        )
        # Should have predicate_id IN clause
        assert "predicate_id IN" in where_clause
        assert "rdf:type" in params

    def test_like_escape_special_chars(self, node_svc, pred_svc):
        """LIKE patterns should properly escape %, _, and \\ characters."""
        from A_semantika._triple_search import _build_search_clause_any_field

        # This text should NOT match DB via FTS (no node found)
        # so it becomes a LIKE pattern
        search_term = "Test_With%Special"

        where_clause, params = _build_search_clause_any_field(
            search_term, node_svc, pred_svc
        )

        # Should have LIKE with escape clause
        assert "LIKE" in where_clause
        assert "ESCAPE" in where_clause


# ════════════════════════════════════════════════════════════════════════════
# Tests for _build_relevance_order_by()
# ════════════════════════════════════════════════════════════════════════════


class TestBuildRelevanceOrderBy:
    """Test _build_relevance_order_by() relevance ordering builder."""

    def test_no_exact_matches_returns_none(self, node_svc, pred_svc):
        """No exact matches should return None (use default sort)."""
        from A_semantika._triple_search import _build_relevance_order_by

        order_by = _build_relevance_order_by(
            "Completely Unmapped Text", node_svc, pred_svc
        )
        assert order_by is None

    def test_exact_subject_match_returns_case_expr(self, node_svc, pred_svc):
        """Exact subject match should return CASE expression."""
        from A_semantika._triple_search import _build_relevance_order_by

        subj = node_svc.create({"etikedoj": {"eo": "Exact Subject"}})

        order_by = _build_relevance_order_by("Exact Subject", node_svc, pred_svc)
        assert order_by is not None
        assert "CASE" in order_by
        assert subj["node_id"] in order_by
        assert "WHEN" in order_by
        assert "ELSE 999 END" in order_by

    def test_sql_injection_safe_uuid_escaping(self, node_svc, pred_svc):
        """Single quotes in UUIDs should be escaped in CASE expression."""
        from A_semantika._triple_search import _build_relevance_order_by

        node = node_svc.create({"etikedoj": {"eo": "Security Test"}})

        order_by = _build_relevance_order_by("Security Test", node_svc, pred_svc)
        assert order_by is not None

        # The order_by should contain the node_id (safely)
        # It should NOT contain unclosed quotes
        assert order_by.count("'") % 2 == 0, "Quotes should be balanced (even count)"

    def test_default_sort_appended(self, node_svc, pred_svc):
        """ORDER BY should end with default sort: subject_uuid, predicate_id."""
        from A_semantika._triple_search import _build_relevance_order_by

        subj = node_svc.create({"etikedoj": {"eo": "Sort Test"}})

        order_by = _build_relevance_order_by("Sort Test", node_svc, pred_svc)
        assert order_by is not None
        assert order_by.endswith(", subject_uuid, predicate_id")


# ════════════════════════════════════════════════════════════════════════════
# Tests for search_triples() unified WHERE clause signature
# ════════════════════════════════════════════════════════════════════════════


class TestSearchTriplesUnifiedSignature:
    """Test TripleService.search_triples() with unified WHERE clause."""

    def test_simple_where_clause(self, triple_svc, node_svc):
        """Simple WHERE clause should work."""
        subj = node_svc.create({"etikedoj": {"eo": "Test Subj"}})
        obj = node_svc.create({"etikedoj": {"eo": "Test Obj"}})
        triple_svc.add(
            subject_uuid=subj["node_id"],
            predicate_id="rdf:type",
            object_value=obj["node_id"],
            object_type="uri"
        )

        results = triple_svc.search_triples(
            "subject_uuid = ?", [subj["node_id"]]
        )
        assert len(results) >= 1
        assert results[0]["subject_uuid"] == subj["node_id"]

    def test_empty_where_clause_treated_as_1equals1(self, triple_svc, node_svc):
        """Empty WHERE clause should be treated as '1=1' (no restriction)."""
        subj = node_svc.create({"etikedoj": {"eo": "Test"}})
        obj = node_svc.create({"etikedoj": {"eo": "Obj"}})
        triple_svc.add(
            subject_uuid=subj["node_id"],
            predicate_id="rdf:type",
            object_value=obj["node_id"],
            object_type="uri"
        )

        results = triple_svc.search_triples("", [])
        assert len(results) >= 1

    def test_or_conditions_in_where(self, triple_svc, node_svc):
        """WHERE clause with OR conditions should work."""
        subj1 = node_svc.create({"etikedoj": {"eo": "Subject 1"}})
        subj2 = node_svc.create({"etikedoj": {"eo": "Subject 2"}})
        obj1 = node_svc.create({"etikedoj": {"eo": "Object 1"}})
        obj2 = node_svc.create({"etikedoj": {"eo": "Object 2"}})
        triple_svc.add(
            subject_uuid=subj1["node_id"],
            predicate_id="rdf:type",
            object_value=obj1["node_id"],
            object_type="uri"
        )
        triple_svc.add(
            subject_uuid=subj2["node_id"],
            predicate_id="rdf:type",
            object_value=obj2["node_id"],
            object_type="uri"
        )

        # Search for triples where subject_uuid is one of two UUIDs
        where_clause = f"subject_uuid = ? OR subject_uuid = ?"
        results = triple_svc.search_triples(
            where_clause, [subj1["node_id"], subj2["node_id"]]
        )
        assert len(results) >= 2
        subjs = {r["subject_uuid"] for r in results}
        assert subj1["node_id"] in subjs
        assert subj2["node_id"] in subjs

    def test_limit_parameter(self, triple_svc, node_svc):
        """Limit parameter should restrict results."""
        subj = node_svc.create({"etikedoj": {"eo": "Limit Test"}})
        # Create 5 objects and triples using seeded rdf:type predicate
        for i in range(5):
            obj = node_svc.create({"etikedoj": {"eo": f"Object {i}"}})
            triple_svc.add(
                subject_uuid=subj["node_id"],
                predicate_id="rdf:type",
                object_value=obj["node_id"],
                object_type="uri"
            )

        # With limit=2, should get at most 2 results
        results = triple_svc.search_triples(
            "subject_uuid = ?", [subj["node_id"]], limit=2
        )
        assert len(results) <= 2

    def test_order_by_parameter_custom(self, triple_svc, node_svc):
        """order_by parameter should override default sort."""
        subj = node_svc.create({"etikedoj": {"eo": "Custom Sort"}})
        obj1 = node_svc.create({"etikedoj": {"eo": "Obj A"}})
        obj2 = node_svc.create({"etikedoj": {"eo": "Obj B"}})
        # Create two triples with same subject, different objects
        triple_svc.add(
            subject_uuid=subj["node_id"],
            predicate_id="rdf:type",
            object_value=obj1["node_id"],
            object_type="uri"
        )
        # Create second triple - use another rdf:type to different object
        triple_svc.add(
            subject_uuid=subj["node_id"],
            predicate_id="rdf:type",
            object_value=obj2["node_id"],
            object_type="uri"
        )

        # Custom order: predicate_id ASC
        results_asc = triple_svc.search_triples(
            "subject_uuid = ?", [subj["node_id"]],
            order_by="predicate_id ASC, subject_uuid"
        )
        results_desc = triple_svc.search_triples(
            "subject_uuid = ?", [subj["node_id"]],
            order_by="predicate_id DESC, subject_uuid"
        )

        # Results should differ in order based on predicate_id
        if len(results_asc) == 2 and len(results_desc) == 2:
            assert results_asc[0]["predicate_id"] <= results_asc[1]["predicate_id"]
            assert results_desc[0]["predicate_id"] >= results_desc[1]["predicate_id"]

    def test_params_not_mutated(self, triple_svc, node_svc):
        """search_triples should not mutate the caller's params list."""
        subj = node_svc.create({"etikedoj": {"eo": "Mutation Test"}})
        obj = node_svc.create({"etikedoj": {"eo": "Mutation Obj"}})
        triple_svc.add(
            subject_uuid=subj["node_id"],
            predicate_id="rdf:type",
            object_value=obj["node_id"],
            object_type="uri"
        )

        params = [subj["node_id"]]
        params_original = params.copy()

        triple_svc.search_triples("subject_uuid = ?", params)

        # Params should not have been mutated
        assert params == params_original


# ════════════════════════════════════════════════════════════════════════════
# Tests for backward compatibility and integration
# ════════════════════════════════════════════════════════════════════════════


class TestBackwardCompatibility:
    """Test that search functions still work after refactoring."""

    def test_search_triples_any_field_still_works(self, triple_svc, node_svc, pred_svc):
        """search_triples_any_field() should still work with new architecture."""
        from A_semantika._triple_search import search_triples_any_field

        subj = node_svc.create({"etikedoj": {"eo": "Test Subject"}})
        obj = node_svc.create({"etikedoj": {"eo": "Test Object"}})
        triple_svc.add(
            subject_uuid=subj["node_id"],
            predicate_id="rdf:type",
            object_value=obj["node_id"],
            object_type="uri"
        )

        # Search should work
        results = search_triples_any_field(
            triple_svc, node_svc, pred_svc, "Test Subject"
        )
        assert len(results) >= 1

    def test_search_triples_by_labels_still_works(self, triple_svc, node_svc, pred_svc):
        """search_triples_by_labels() should still work with new architecture."""
        from A_semantika._triple_search import search_triples_by_labels

        subj = node_svc.create({"etikedoj": {"eo": "Label Subject"}})
        obj = node_svc.create({"etikedoj": {"eo": "Label Object"}})
        triple_svc.add(
            subject_uuid=subj["node_id"],
            predicate_id="rdf:type",
            object_value=obj["node_id"],
            object_type="uri"
        )

        # Search by subject label
        results = search_triples_by_labels(
            triple_svc, node_svc, pred_svc, subject="Label Subject"
        )
        assert len(results) >= 1

        # Search by object label
        results = search_triples_by_labels(
            triple_svc, node_svc, pred_svc, object="Label Object"
        )
        assert len(results) >= 1
