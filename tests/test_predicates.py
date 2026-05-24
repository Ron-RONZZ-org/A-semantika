"""Tests for PredicateService — CRUD, search."""
from __future__ import annotations

import json


class TestPredicateCreate:
    """Predicate creation tests."""

    def test_create_minimal(self, pred_svc) -> None:
        """Creating a predicate with minimal data should work."""
        pred = pred_svc.create({
            "predicate_id": "wdt:P31",
            "etikedoj": {"eo": "estas tipo de"},
        })
        assert pred["predicate_id"] == "wdt:P31"
        etikedoj = json.loads(pred["etikedoj"])
        assert etikedoj.get("eo") == "estas tipo de"
        # Predicate uses predicate_id as PK (no synthetic uuid)
        assert "uuid" not in pred

    def test_create_duplicate_predicate_id_raises(self, pred_svc) -> None:
        """Duplicate predicate_id should raise."""
        pred_svc.create({"predicate_id": "wdt:P31", "etikedoj": {"eo": "tipo"}})
        import pytest
        with pytest.raises(Exception):
            pred_svc.create({"predicate_id": "wdt:P31", "etikedoj": {"eo": "tipo denove"}})

    def test_create_with_priskriboj(self, pred_svc) -> None:
        """Creating with priskriboj should work."""
        pred = pred_svc.create({
            "predicate_id": "wdt:P31",
            "etikedoj": {"eo": "tipo", "en": "type"},
            "priskriboj": {"eo": "Priskribo", "en": "Description"},
        })
        assert json.loads(pred["etikedoj"]) == {"eo": "tipo", "en": "type"}
        assert json.loads(pred["priskriboj"]) == {"eo": "Priskribo", "en": "Description"}


class TestPredicateRead:
    """Predicate read tests."""

    def test_get_by_predicate_id(self, pred_svc) -> None:
        """get_by_predicate_id should work."""
        pred_svc.create({"predicate_id": "wdt:P31", "etikedoj": {"eo": "tipo"}})
        fetched = pred_svc.get_by_predicate_id("wdt:P31")
        assert fetched is not None
        assert json.loads(fetched["etikedoj"])["eo"] == "tipo"

    def test_get_by_predicate_id_nonexistent(self, pred_svc) -> None:
        """Nonexistent predicate_id should return None."""
        assert pred_svc.get_by_predicate_id("nonexistent") is None


class TestPredicateSearch:
    """Predicate search tests."""

    def test_search_by_id(self, pred_svc) -> None:
        """Search by predicate_id should work."""
        pred_svc.create({"predicate_id": "wdt:P31", "etikedoj": {"eo": "tipo"}})
        pred_svc.create({"predicate_id": "wdt:P1082", "etikedoj": {"eo": "logxantaro"}})

        results = pred_svc.search("wdt:P31")
        assert len(results) >= 1
        assert results[0]["predicate_id"] == "wdt:P31"

    def test_search_by_label(self, pred_svc) -> None:
        """Search by label text (from etikedoj JSON) should work."""
        pred_svc.create({"predicate_id": "wdt:P31", "etikedoj": {"eo": "estas tipo de"}})
        results = pred_svc.search("tipo")
        assert len(results) >= 1

    def test_search_case_insensitive(self, pred_svc) -> None:
        """Search should be case-insensitive via COLLATE NOCASE."""
        pred_svc.create({"predicate_id": "WDT:P31", "etikedoj": {"eo": "tipo"}})
        results_lower = pred_svc.search("wdt:p31")
        assert len(results_lower) >= 1
        results_mixed = pred_svc.search("Wdt:P")
        assert len(results_mixed) >= 1

    def test_search_with_percent_escaped(self, pred_svc) -> None:
        """LIKE wildcard % in query should be escaped, not expanded."""
        # Create data containing a literal % character
        pred_svc.create({"predicate_id": "wdt:P100pct", "etikedoj": {"eo": "100% completed"}})
        # Searching for "100%" should match the literal "100%" in the label
        results = pred_svc.search("100%")
        assert len(results) >= 1
        # Searching for a bare "%" should only match literal "%" in data
        results_pct = pred_svc.search("%")
        assert len(results_pct) >= 1  # matches the "%" in "100% completed"

    def test_search_with_underscore_escaped(self, pred_svc) -> None:
        """LIKE wildcard _ in query should be escaped, not expanded."""
        pred_svc.create({"predicate_id": "wdt:P_AB", "etikedoj": {"eo": "underscore test"}})
        # Searching for "P_AB" should match literally (not "P" + any 3 chars)
        results = pred_svc.search("P_AB")
        assert len(results) >= 1
        # Searching for "P_" should only match literal "P_", not
        # "P" + any single char. "wdt:P_AB" does contain "P_" → 1 match.
        results_under = pred_svc.search("P_")
        assert len(results_under) >= 1
        # Before escaping, "P__" (double wildcard) could also match "P_AB".
        # Now it only matches literal "P__".
        results_double = pred_svc.search("P__")
        assert len(results_double) == 0


class TestPredicateUpdate:
    """Predicate update tests."""

    def test_update_label(self, pred_svc) -> None:
        """Updating a predicate label should work."""
        pred = pred_svc.create({"predicate_id": "wdt:P31", "etikedoj": {"eo": "tipo"}})
        pred_svc.update(pred["predicate_id"], {"etikedoj": {"eo": "tipo", "en": "instance of"}})
        updated = pred_svc.get_by_predicate_id("wdt:P31")
        assert updated is not None
        etikedoj = json.loads(updated["etikedoj"])
        assert etikedoj["en"] == "instance of"
        assert etikedoj["eo"] == "tipo"  # unchanged