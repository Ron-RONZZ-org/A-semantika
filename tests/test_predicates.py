"""Tests for PredicateService — CRUD, search, FTS5."""
from __future__ import annotations


class TestPredicateCreate:
    """Predicate creation tests."""

    def test_create_minimal(self, pred_svc) -> None:
        """Creating a predicate with minimal data should work."""
        pred = pred_svc.create({
            "predicate_id": "wdt:P31",
            "label_eo": "estas tipo de",
        })
        assert pred["predicate_id"] == "wdt:P31"
        assert pred["label_eo"] == "estas tipo de"
        assert pred["uuid"] is not None

    def test_create_duplicate_predicate_id_raises(self, pred_svc) -> None:
        """Duplicate predicate_id should raise."""
        pred_svc.create({"predicate_id": "wdt:P31", "label_eo": "tipo"})
        import pytest
        with pytest.raises(Exception):
            pred_svc.create({"predicate_id": "wdt:P31", "label_eo": "tipo denove"})


class TestPredicateRead:
    """Predicate read tests."""

    def test_get_by_predicate_id(self, pred_svc) -> None:
        """get_by_predicate_id should work."""
        pred_svc.create({"predicate_id": "wdt:P31", "label_eo": "tipo"})
        fetched = pred_svc.get_by_predicate_id("wdt:P31")
        assert fetched is not None
        assert fetched["label_eo"] == "tipo"

    def test_get_by_predicate_id_nonexistent(self, pred_svc) -> None:
        """Nonexistent predicate_id should return None."""
        assert pred_svc.get_by_predicate_id("nonexistent") is None


class TestPredicateSearch:
    """Predicate search tests."""

    def test_search_by_id(self, pred_svc) -> None:
        """Search by predicate_id should work."""
        pred_svc.create({"predicate_id": "wdt:P31", "label_eo": "tipo"})
        pred_svc.create({"predicate_id": "wdt:P1082", "label_eo": "logxantaro"})

        results = pred_svc.search("wdt:P31")
        assert len(results) >= 1
        assert results[0]["predicate_id"] == "wdt:P31"

    def test_search_by_label(self, pred_svc) -> None:
        """Search by label text should work."""
        pred_svc.create({"predicate_id": "wdt:P31", "label_eo": "estas tipo de"})
        results = pred_svc.search("tipo")
        assert len(results) >= 1


class TestPredicateUpdate:
    """Predicate update tests."""

    def test_update_label(self, pred_svc) -> None:
        """Updating a predicate label should work."""
        pred = pred_svc.create({"predicate_id": "wdt:P31", "label_eo": "tipo"})
        pred_svc.update(pred["uuid"], {"label_en": "instance of"})
        updated = pred_svc.get_by_predicate_id("wdt:P31")
        assert updated is not None
        assert updated["label_en"] == "instance of"
        assert updated["label_eo"] == "tipo"  # unchanged
