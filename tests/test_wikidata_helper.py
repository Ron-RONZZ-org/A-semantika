"""Tests for _wikidata_helper.py — validation, normalization, search, fetch.

All Wikidata API calls are mocked — no network access.
"""
from __future__ import annotations

from unittest.mock import patch

from A_semantika._wikidata_helper import (
    fetch_wikidata_details,
    is_wikidata_id,
    normalize_predicate_id,
    search_wikidata,
)


# ── is_wikidata_id ────────────────────────────────────────────────────────────


class TestIsWikidataId:
    """Pattern matching for Wikidata property IDs."""

    def test_wdt_prefix(self) -> None:
        assert is_wikidata_id("wdt:P31") is True

    def test_bare_p_number(self) -> None:
        assert is_wikidata_id("P31") is True

    def test_large_p_number(self) -> None:
        assert is_wikidata_id("P1082") is True

    def test_case_insensitive_wdt(self) -> None:
        assert is_wikidata_id("WDT:P1082") is True

    def test_non_wikidata_id(self) -> None:
        assert is_wikidata_id("rdf:type") is False

    def test_custom_prefix(self) -> None:
        assert is_wikidata_id("my:prop") is False

    def test_foaf_relation(self) -> None:
        assert is_wikidata_id("foaf:knows") is False

    def test_empty_string(self) -> None:
        assert is_wikidata_id("") is False

    def test_p_without_digits(self) -> None:
        assert is_wikidata_id("P") is False


# ── normalize_predicate_id ────────────────────────────────────────────────────


class TestNormalizePredicateId:
    """Normalization of bare P-numbers to wdt: prefix."""

    def test_bare_to_wdt(self) -> None:
        assert normalize_predicate_id("P31") == "wdt:P31"

    def test_already_normalized(self) -> None:
        assert normalize_predicate_id("wdt:P31") == "wdt:P31"

    def test_lowercase_uppercased(self) -> None:
        assert normalize_predicate_id("p31") == "wdt:P31"

    def test_lowercase_wdt(self) -> None:
        assert normalize_predicate_id("wdt:p31") == "wdt:P31"

    def test_non_wikidata_unchanged(self) -> None:
        assert normalize_predicate_id("rdf:type") == "rdf:type"

    def test_custom_prefix_unchanged(self) -> None:
        assert normalize_predicate_id("my:prop") == "my:prop"

    def test_empty_string(self) -> None:
        assert normalize_predicate_id("") == ""

    def test_whitespace_stripped(self) -> None:
        assert normalize_predicate_id("  P31  ") == "wdt:P31"

    def test_wdt_with_extra_colons(self) -> None:
        assert normalize_predicate_id("wdt:P1082") == "wdt:P1082"


# ── search_wikidata (mocked) ──────────────────────────────────────────────────


class TestSearchWikidata:
    """Wikidata search with mocked API."""

    @patch("A_semantika._wikidata_helper.search_properties")
    def test_returns_mapped_results(self, mock_search) -> None:
        mock_search.return_value = [
            {
                "ligilo": "wdt:P31",
                "etikedo": "instance of",
                "priskribo": "that class of which this subject is a particular example and member",
                "aliasoj": ["is a", "p31"],
                "fonto": "wikidata",
            },
            {
                "ligilo": "wdt:P1082",
                "etikedo": "population",
                "priskribo": "number of inhabitants",
                "aliasoj": ["pop", "p1082"],
                "fonto": "wikidata",
            },
        ]
        results = search_wikidata("instance")
        assert len(results) == 2
        assert results[0]["predicate_id"] == "wdt:P31"
        assert results[0]["label"] == "instance of"
        assert results[0]["source"] == "wikidata"
        # Check aliases serialized as JSON
        import json
        aliases = json.loads(results[0]["aliases"])
        assert "is a" in aliases

    @patch("A_semantika._wikidata_helper.search_properties")
    def test_empty_results(self, mock_search) -> None:
        mock_search.return_value = []
        results = search_wikidata("xyzzy_nonexistent")
        assert results == []

    @patch("A_semantika._wikidata_helper.search_properties")
    def test_network_failure_returns_empty(self, mock_search) -> None:
        mock_search.side_effect = RuntimeError("Network error")
        results = search_wikidata("anything")
        assert results == []

    @patch("A_semantika._wikidata_helper.search_properties")
    def test_passes_timeout(self, mock_search) -> None:
        mock_search.return_value = []
        search_wikidata("test", timeout=3.0)
        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs["timeout"] == 3.0


# ── fetch_wikidata_details (mocked) ───────────────────────────────────────────


class TestFetchWikidataDetails:
    """Wikidata per-language details fetch with mocked API."""

    @patch("A_semantika._wikidata_helper.get_property_details")
    def test_returns_properly_mapped(self, mock_details) -> None:
        mock_details.return_value = {
            "id": "P1082",
            "labels": {"en": "population", "eo": "loĝantaro"},
            "descriptions": {
                "en": "number of inhabitants",
                "eo": "nombro da loĝantoj",
            },
            "aliases": {
                "en": ["pop", "p1082"],
                "eo": ["loĝantaroj", "p1082"],
            },
        }
        result = fetch_wikidata_details("wdt:P1082")
        assert result is not None
        assert result["predicate_id"] == "wdt:P1082"
        assert result["label_eo"] == "loĝantaro"
        assert result["label_en"] == "population"
        assert result["priskribo"] == "nombro da loĝantoj"
        assert result["source"] == "wikidata"

    @patch("A_semantika._wikidata_helper.get_property_details")
    def test_handles_bare_p_number(self, mock_details) -> None:
        mock_details.return_value = {
            "id": "P31",
            "labels": {"en": "instance of", "eo": "estas ekzemplo de"},
            "descriptions": {},
            "aliases": {},
        }
        result = fetch_wikidata_details("P31")
        assert result is not None
        assert result["predicate_id"] == "wdt:P31"
        assert result["label_eo"] == "estas ekzemplo de"

    @patch("A_semantika._wikidata_helper.get_property_details")
    def test_network_failure_returns_none(self, mock_details) -> None:
        mock_details.side_effect = RuntimeError("Network error")
        result = fetch_wikidata_details("P31")
        assert result is None

    @patch("A_semantika._wikidata_helper.get_property_details")
    def test_missing_languages_graceful(self, mock_details) -> None:
        """When the property has no eo label, label_eo should be empty."""
        mock_details.return_value = {
            "id": "P999",
            "labels": {"fr": "test"},
            "descriptions": {"fr": "description"},
            "aliases": {"fr": ["test_alias"]},
        }
        result = fetch_wikidata_details("P999")
        assert result is not None
        assert result["label_eo"] == ""
        assert result["label_en"] == ""
        assert result["priskribo"] == ""  # fr not in priority languages default: eo, en

    @patch("A_semantika._wikidata_helper.get_property_details")
    def test_passes_timeout(self, mock_details) -> None:
        mock_details.return_value = {
            "id": "P31",
            "labels": {"en": "instance of"},
            "descriptions": {},
            "aliases": {},
        }
        fetch_wikidata_details("P31", timeout=5.0)
        mock_details.assert_called_once()
        _, kwargs = mock_details.call_args
        assert kwargs["timeout"] == 5.0
