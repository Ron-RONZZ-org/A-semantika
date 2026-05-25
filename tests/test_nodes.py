"""Tests for NodeService — CRUD, FTS5 search, label denormalization, node_id prefix resolution."""
from __future__ import annotations

import json

from A_semantika._node_helpers import get_display_label


class TestNodeCreate:
    """Node creation tests."""

    def test_create_minimal(self, node_svc) -> None:
        """Creating a node with minimal data should work."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        assert node["node_id"] is not None
        assert node["node_id"] != ""
        assert json.loads(node["etikedoj"]) == {"eo": "Hundo"}
        assert node["label_text"] == "Hundo"
        assert node["kreita_je"] is not None

    def test_create_with_custom_id(self, node_svc) -> None:
        """Creating with custom node_id should respect it."""
        custom_id = "SPACO"
        node = node_svc.create({"node_id": custom_id, "etikedoj": {"eo": "Kato"}})
        assert node["node_id"] == custom_id

    def test_create_with_definitions(self, node_svc) -> None:
        """Definitions should be stored and denormalized."""
        node = node_svc.create({
            "etikedoj": {"eo": "Hundo"},
            "difinoj": {"eo": "Mamulo", "en": "Dog"},
        })
        assert json.loads(node["difinoj"]) == {"eo": "Mamulo", "en": "Dog"}
        assert "Mamulo" in node["difin_text"]

    def test_create_duplicate_id_raises(self, node_svc) -> None:
        """Creating with a duplicate node_id should fail."""
        node_svc.create({"node_id": "DUPLICATO", "etikedoj": {"eo": "Test"}})
        import pytest
        with pytest.raises(Exception):
            node_svc.create({"node_id": "DUPLICATO", "etikedoj": {"eo": "Test2"}})

    def test_create_duplicate_id_value_error_message(self, node_svc) -> None:
        """Duplicate node_id should raise ValueError with 'already exists' message."""
        id_val = "Ripetato"
        node_svc.create({"node_id": id_val, "etikedoj": {"eo": "Unua"}})
        import pytest
        with pytest.raises(ValueError, match="already exists") as exc_info:
            node_svc.create({"node_id": id_val, "etikedoj": {"eo": "Dua"}})
        assert "modifi" in str(exc_info.value)


class TestNodeRead:
    """Node read/get tests."""

    def test_get(self, node_svc) -> None:
        """Getting a node by node_id should work."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        fetched = node_svc.get(node["node_id"])
        assert fetched is not None
        assert fetched["node_id"] == node["node_id"]

    def test_get_nonexistent(self, node_svc) -> None:
        """Getting a nonexistent node should return None."""
        assert node_svc.get("nonexistent-id") is None


class TestNodeUpdate:
    """Node update tests."""

    def test_update_label(self, node_svc) -> None:
        """Updating etikedoj should re-denormalize label_text."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        updated = node_svc.update(node["node_id"], {"etikedoj": {"eo": "Hundo2", "en": "Dog"}})
        assert json.loads(updated["etikedoj"]) == {"eo": "Hundo2", "en": "Dog"}
        assert updated["label_text"] == "Hundo2 Dog"
        assert updated["modifita_je"] is not None
        assert updated["modifita_je"] != node["kreita_je"]

    def test_update_partial(self, node_svc) -> None:
        """Updating only some fields should leave others intact."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}, "difinoj": {"eo": "Mamulo"}})
        updated = node_svc.update(node["node_id"], {"difinoj": {"en": "Canine"}})
        assert json.loads(updated["difinoj"]) == {"en": "Canine"}
        assert json.loads(updated["etikedoj"]) == {"eo": "Hundo"}


class TestNodeDelete:
    """Node delete tests."""

    def test_delete(self, node_svc) -> None:
        """Deleting a node should remove it."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        node_svc.delete(node["node_id"])
        assert node_svc.get(node["node_id"]) is None

    def test_delete_nonexistent(self, node_svc) -> None:
        """Deleting a nonexistent node should not raise (CRUDService silently ignores)."""
        node_svc.delete("nonexistent-id")


class TestNodeSearch:
    """Node FTS5 search tests."""

    def test_search_by_label(self, node_svc) -> None:
        """Searching by label text should work via FTS."""
        node_svc.create({"etikedoj": {"eo": "Hundo"}})
        node_svc.create({"etikedoj": {"eo": "Kato"}})
        node_svc.create({"etikedoj": {"eo": "Birdo"}})

        results = node_svc.search("Hundo")
        assert len(results) >= 1
        assert any("Hundo" in json.loads(r["etikedoj"]).get("eo", "") for r in results)

        results = node_svc.search("Birdo")
        assert len(results) >= 1

    def test_search_empty_query_returns_all(self, node_svc) -> None:
        """Empty search query should list all nodes."""
        node_svc.create({"etikedoj": {"eo": "Hundo"}})
        node_svc.create({"etikedoj": {"eo": "Kato"}})
        results = node_svc.search("")
        assert len(results) >= 2

    def test_search_no_match(self, node_svc) -> None:
        """Searching with no matches should return empty list."""
        node_svc.create({"etikedoj": {"eo": "Hundo"}})
        results = node_svc.search("xyzzy_nonexistent")
        assert len(results) == 0


class TestNodeGetExact:
    """NodeService.get() must use exact match, not LIKE prefix."""

    def test_get_exact_match_only(self, node_svc) -> None:
        """get() must match the exact node_id, not a prefix."""
        node_svc.create({"node_id": "AAA", "etikedoj": {"eo": "A"}})
        node_svc.create({"node_id": "AAAB", "etikedoj": {"eo": "B"}})
        fetched = node_svc.get("AAA")
        assert fetched is not None
        assert fetched["node_id"] == "AAA"
        # Should NOT return AAAB
        assert fetched["node_id"] != "AAAB"

    def test_get_exact_case_insensitive(self, node_svc) -> None:
        """get() should be case-insensitive (COLLATE NOCASE)."""
        node_svc.create({"node_id": "SPACO", "etikedoj": {"eo": "Spaco"}})
        fetched = node_svc.get("spaco")
        assert fetched is not None
        assert fetched["node_id"] == "SPACO"

    def test_get_nonexistent_case_insensitive(self, node_svc) -> None:
        """get() should return None for nonexistent ID regardless of case."""
        node_svc.create({"node_id": "MAMULO", "etikedoj": {"eo": "Mamulo"}})
        fetched = node_svc.get("mamuloWRONG")
        assert fetched is None


class TestNodeIdPrefix:
    """node_id prefix resolution tests."""

    def test_resolve_prefix(self, node_svc) -> None:
        """Resolving a node_id prefix should find the node."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        prefix = node["node_id"][:16]
        resolved = node_svc.resolve_uuid_prefix(prefix)
        assert resolved is not None
        assert resolved["node_id"] == node["node_id"]

    def test_resolve_exact_human_id(self, node_svc) -> None:
        """A human-readable ID like SPACO should be resolvable directly."""
        node_svc.create({"node_id": "SPACO", "etikedoj": {"eo": "Spaco"}})
        resolved = node_svc.resolve_uuid_prefix("SPACO")
        assert resolved is not None
        assert resolved["node_id"] == "SPACO"

    def test_resolve_prefix_human_id(self, node_svc) -> None:
        """Prefix resolution should work for human-readable IDs too."""
        node_svc.create({"node_id": "HOMOTEST", "etikedoj": {"eo": "Homo"}})
        resolved = node_svc.resolve_uuid_prefix("HOMO")
        assert resolved is not None
        assert resolved["node_id"] == "HOMOTEST"

    def test_resolve_ambiguous_prefix(self, node_svc) -> None:
        """Ambiguous prefix should raise ValueError."""
        node_svc.create({"node_id": "AAAA", "etikedoj": {"eo": "A"}})
        node_svc.create({"node_id": "AAAB", "etikedoj": {"eo": "B"}})
        import pytest
        with pytest.raises(ValueError, match="ambiguous"):
            node_svc.resolve_uuid_prefix("AAA")

    def test_resolve_nonexistent_prefix(self, node_svc) -> None:
        """Nonexistent prefix should return None."""
        resolved = node_svc.resolve_uuid_prefix("ZZZZZZZZ")
        assert resolved is None

    # ── Issue #1: Case-insensitive resolution ───────────────────────────

    def test_resolve_case_insensitive_exact(self, node_svc) -> None:
        """resolve_uuid_prefix should find exact match case-insensitively."""
        node_svc.create({"node_id": "SPACO", "etikedoj": {"eo": "Spaco"}})
        resolved = node_svc.resolve_uuid_prefix("spaco")
        assert resolved is not None
        assert resolved["node_id"] == "SPACO"

    def test_resolve_case_insensitive_prefix(self, node_svc) -> None:
        """resolve_uuid_prefix should find prefix match case-insensitively."""
        node_svc.create({"node_id": "MAMULO", "etikedoj": {"eo": "Mamulo"}})
        resolved = node_svc.resolve_uuid_prefix("mam")
        assert resolved is not None
        assert resolved["node_id"] == "MAMULO"

    def test_resolve_case_insensitive_ambiguous(self, node_svc) -> None:
        """Case-insensitive prefix should detect ambiguity across cases."""
        node_svc.create({"node_id": "AAA", "etikedoj": {"eo": "A"}})
        node_svc.create({"node_id": "aaa", "etikedoj": {"eo": "a"}})
        node_svc.create({"node_id": "AAb", "etikedoj": {"eo": "Ab"}})
        import pytest
        # "aa" matches "AAA", "aaa", "AAb" case-insensitively → ambiguous
        with pytest.raises(ValueError, match="ambiguous"):
            node_svc.resolve_uuid_prefix("aa")

    # ── Issue #3: LIKE wildcard escaping ────────────────────────────────

    def test_resolve_prefix_with_underscore(self, node_svc) -> None:
        """Prefix with '_' must not act as LIKE wildcard (single-char match)."""
        node_svc.create({"node_id": "test_1", "etikedoj": {"eo": "Test1"}})
        node_svc.create({"node_id": "testX1", "etikedoj": {"eo": "TestX1"}})
        # "test_" should match ONLY "test_1", NOT "testX1" (if _ is escaped)
        resolved = node_svc.resolve_uuid_prefix("test_")
        assert resolved is not None
        assert resolved["node_id"] == "test_1"

    def test_resolve_prefix_with_percent(self, node_svc) -> None:
        """Prefix with '%' must not act as LIKE wildcard."""
        node_svc.create({"node_id": "test%1", "etikedoj": {"eo": "TestPct1"}})
        node_svc.create({"node_id": "testX1", "etikedoj": {"eo": "TestX1"}})
        resolved = node_svc.resolve_uuid_prefix("test%")
        assert resolved is not None
        assert resolved["node_id"] == "test%1"


class TestNodeTrashOlderThan:
    """get_trash_older_than SQL-side date filtering tests."""

    def test_get_trash_older_than_positive_days_excludes_fresh(self, node_svc) -> None:
        """get_trash_older_than with positive days should exclude freshly deleted items.

        A freshly deleted item (forigita_je ≈ now) is NOT older than 1 day.
        """
        node_svc.create({"node_id": "FRESH", "etikedoj": {"eo": "Fresh"}})
        node_svc.delete("FRESH", soft=True)
        # 1 day old → delete items where forigita_je < (now - 1day)
        # Freshly deleted items are NOT older than 1 day
        items = node_svc.get_trash_older_than(1)
        assert len(items) == 0

    def test_get_trash_older_than_negative_days_matches_all(self, node_svc) -> None:
        """get_trash_older_than with negative days should match all trashed items.

        Negative days means forigita_je < (now + N days) — a date in the future,
        so all items match.
        """
        node_svc.create({"node_id": "ANY", "etikedoj": {"eo": "Any"}})
        node_svc.delete("ANY", soft=True)
        items = node_svc.get_trash_older_than(-1)
        assert len(items) >= 1

    def test_get_trash_older_than_with_limit(self, node_svc) -> None:
        """get_trash_older_than should respect the limit parameter."""
        for i in range(5):
            node_svc.create({"node_id": f"OLD{i}", "etikedoj": {"eo": f"Old{i}"}})
            node_svc.delete(f"OLD{i}", soft=True)
        # Negative days means "older than -N days ago" = in the future → matches all
        # But limit=2 should cap results
        items = node_svc.get_trash_older_than(-1, limit=2)
        assert len(items) <= 2


class TestNodeDisplayLabel:
    """Display label resolution tests."""

    def test_get_display_label_eo(self, node_svc) -> None:
        """Display label should prefer eo."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo", "en": "Dog"}})
        label, lang = get_display_label(node_svc.resolve_uuid_prefix, node["node_id"])
        assert label == "Hundo"
        assert lang == "eo"

    def test_get_display_label_en_fallback(self, node_svc) -> None:
        """Display label should fall back to en."""
        node = node_svc.create({"etikedoj": {"en": "Dog"}})
        label, lang = get_display_label(node_svc.resolve_uuid_prefix, node["node_id"])
        assert label == "Dog"
        assert lang == "en"

    def test_get_display_label_fallback_id(self, node_svc) -> None:
        """Display label with no labels should return node_id prefix."""
        node = node_svc.create({"etikedoj": {}})
        label, lang = get_display_label(node_svc.resolve_uuid_prefix, node["node_id"])
        assert label == node["node_id"][:16]
        assert lang == ""

    def test_get_display_label_nonexistent(self, node_svc) -> None:
        """Nonexistent node_id should return the input as-is."""
        label, lang = get_display_label(node_svc.resolve_uuid_prefix, "nonexistent")
        assert label == "nonexistent"
        assert lang == ""
