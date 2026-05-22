"""Tests for NodeService — CRUD, FTS5 search, label denormalization, UUID prefix resolution."""
from __future__ import annotations

import json


class TestNodeCreate:
    """Node creation tests."""

    def test_create_minimal(self, node_svc) -> None:
        """Creating a node with minimal data should work."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        assert node["uuid"] is not None
        assert len(node["uuid"]) == 36
        assert json.loads(node["etikedoj"]) == {"eo": "Hundo"}
        assert node["label_text"] == "Hundo"
        assert node["kreita_je"] is not None

    def test_create_with_custom_uuid(self, node_svc) -> None:
        """Creating with custom UUID should respect it."""
        custom_uuid = "12345678-1234-1234-1234-123456789abc"
        node = node_svc.create({"uuid": custom_uuid, "etikedoj": {"eo": "Kato"}})
        assert node["uuid"] == custom_uuid

    def test_create_with_definitions(self, node_svc) -> None:
        """Definitions should be stored and denormalized."""
        node = node_svc.create({
            "etikedoj": {"eo": "Hundo"},
            "difinoj": {"eo": "Mamulo", "en": "Dog"},
        })
        assert json.loads(node["difinoj"]) == {"eo": "Mamulo", "en": "Dog"}
        assert "Mamulo" in node["difin_text"]

    def test_create_duplicate_uuid_raises(self, node_svc) -> None:
        """Creating with a duplicate UUID should fail."""
        node_svc.create({"uuid": "a" * 36, "etikedoj": {"eo": "Test"}})
        import pytest
        with pytest.raises(Exception):
            node_svc.create({"uuid": "a" * 36, "etikedoj": {"eo": "Test2"}})


class TestNodeRead:
    """Node read/get tests."""

    def test_get(self, node_svc) -> None:
        """Getting a node by UUID should work."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        fetched = node_svc.get(node["uuid"])
        assert fetched is not None
        assert fetched["uuid"] == node["uuid"]

    def test_get_nonexistent(self, node_svc) -> None:
        """Getting a nonexistent node should return None."""
        assert node_svc.get("nonexistent-uuid") is None


class TestNodeUpdate:
    """Node update tests."""

    def test_update_label(self, node_svc) -> None:
        """Updating etikedoj should re-denormalize label_text."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        updated = node_svc.update(node["uuid"], {"etikedoj": {"eo": "Hundo2", "en": "Dog"}})
        assert json.loads(updated["etikedoj"]) == {"eo": "Hundo2", "en": "Dog"}
        assert updated["label_text"] == "Hundo2 Dog"
        assert updated["modifita_je"] is not None
        assert updated["modifita_je"] != node["kreita_je"]

    def test_update_partial(self, node_svc) -> None:
        """Updating only some fields should leave others intact."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}, "difinoj": {"eo": "Mamulo"}})
        updated = node_svc.update(node["uuid"], {"difinoj": {"en": "Canine"}})
        assert json.loads(updated["difinoj"]) == {"en": "Canine"}
        assert json.loads(updated["etikedoj"]) == {"eo": "Hundo"}


class TestNodeDelete:
    """Node delete tests."""

    def test_delete(self, node_svc) -> None:
        """Deleting a node should remove it."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        node_svc.delete(node["uuid"])
        assert node_svc.get(node["uuid"]) is None

    def test_delete_nonexistent(self, node_svc) -> None:
        """Deleting a nonexistent node should not raise (CRUDService silently ignores)."""
        # CRUDService.delete() returns silently on nonexistent UUID
        node_svc.delete("nonexistent-uuid")


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


class TestNodeUUIDPrefix:
    """UUID prefix resolution tests."""

    def test_resolve_prefix(self, node_svc) -> None:
        """Resolving a UUID prefix should find the node."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        prefix = node["uuid"][:8]
        resolved = node_svc.resolve_uuid_prefix(prefix)
        assert resolved is not None
        assert resolved["uuid"] == node["uuid"]

    def test_resolve_ambiguous_prefix(self, node_svc) -> None:
        """Ambiguous prefix should raise ValueError."""
        node_svc.create({"uuid": "aaaaaaaa-1111-1111-1111-111111111111", "etikedoj": {"eo": "A"}})
        node_svc.create({"uuid": "aaaaaaab-2222-2222-2222-222222222222", "etikedoj": {"eo": "B"}})
        # "aaaa" matches both
        import pytest
        with pytest.raises(ValueError, match="ambiguous"):
            node_svc.resolve_uuid_prefix("aaaa")

    def test_resolve_nonexistent_prefix(self, node_svc) -> None:
        """Nonexistent prefix should return None."""
        resolved = node_svc.resolve_uuid_prefix("zzzzzzzz")
        assert resolved is None


class TestNodeDisplayLabel:
    """Display label resolution tests."""

    def test_get_display_label_eo(self, node_svc) -> None:
        """Display label should prefer eo."""
        node = node_svc.create({"etikedoj": {"eo": "Hundo", "en": "Dog"}})
        label, lang = node_svc.get_display_label(node["uuid"])
        assert label == "Hundo"
        assert lang == "eo"

    def test_get_display_label_en_fallback(self, node_svc) -> None:
        """Display label should fall back to en."""
        node = node_svc.create({"etikedoj": {"en": "Dog"}})
        label, lang = node_svc.get_display_label(node["uuid"])
        assert label == "Dog"
        assert lang == "en"

    def test_get_display_label_fallback_uuid(self, node_svc) -> None:
        """Display label with no labels should return UUID prefix."""
        node = node_svc.create({"etikedoj": {}})
        label, lang = node_svc.get_display_label(node["uuid"])
        assert label == node["uuid"][:8]
        assert lang == ""

    def test_get_display_label_nonexistent(self, node_svc) -> None:
        """Nonexistent UUID should return the input as-is."""
        label, lang = node_svc.get_display_label("nonexistent")
        assert label == "nonexistent"
        assert lang == ""
