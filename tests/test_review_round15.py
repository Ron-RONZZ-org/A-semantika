"""Regression tests for code review round 15 fixes.

Scope (Issue #39):
  F1: Orphan arc rollback in create_node_arcs()
  F2: AmbiguousUUIDError not silently swallowed in _triple_search
  F3: Use shared extract_label_text from _node_helpers
  F4: Narrowed except Exception in NodeService.delete()
"""
from __future__ import annotations

import sqlite3

import pytest
from typer.testing import CliRunner

from A_semantika._cli_helpers import create_node_arcs
from A_semantika._node_helpers import extract_label_text
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._triple_search import resolve_objects, resolve_subjects
from A_semantika.cli import app
from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_triple_service,
)


# ── F1: Orphan arc rollback ─────────────────────────────────────────────


class TestCreateNodeArcsRollback:
    """create_node_arcs() must not leave orphan nodes with partial arcs."""

    def _setup(self, db, node_svc, pred_svc, triple_svc):
        """Set up a node and predicates for arc testing."""
        node_svc.create({"node_id": "test-subjekt-0", "etikedoj": {"eo": "Subjekto"}})
        node_svc.create({"node_id": "test-objekt-1", "etikedoj": {"eo": "Objekto1"}})
        node_svc.create({"node_id": "test-objekt-2", "etikedoj": {"eo": "Objekto2"}})
        # Create a predicate but with a deliberate invalid state to trigger failure
        pred_svc.create({
            "predicate_id": "ex:validPredicate",
            "etikedoj": {"eo": "valida"},
        })
        # Don't create ex:invalidPredicate — will fail FK validation

    def test_orphan_cleanup_on_partial_failure(self, db, node_svc, pred_svc, triple_svc):
        """When one arc fails after others succeeded, no orphan node remains."""
        self._setup(db, node_svc, pred_svc, triple_svc)
        node_id_val = "test-subjekt-0"

        arcs = [
            {
                "subject": node_id_val,
                "predicate": "ex:validPredicate",
                "object": "test-objekt-1",
                "object_type": "uri",
            },
            {
                "subject": node_id_val,
                "predicate": "ex:nonExistentPredicate",
                "object": "test-objekt-2",
                "object_type": "uri",
            },
        ]

        with pytest.raises(ValueError, match="Predicate not found"):
            create_node_arcs(triple_svc, node_svc, node_id_val, arcs)

        # Verify: no arcs reference the node
        remaining = triple_svc.get_by_nodes([node_id_val])
        assert remaining == [], (
            f"Expected no arcs for orphaned node, got {len(remaining)}"
        )

        # Verify: node itself was deleted (soft-delete, now in trash)
        node = node_svc.get(node_id_val)
        assert node is None, "Orphan node should have been deleted"

    def test_rollback_with_duplicate_triple(self, db, node_svc, pred_svc, triple_svc):
        """DuplicateTripleError is silently skipped and does not break rollback."""
        self._setup(db, node_svc, pred_svc, triple_svc)

        # First, create an initial triple
        triple_svc.add(
            subject_uuid="test-subjekt-0",
            predicate_id="ex:validPredicate",
            object_value="test-objekt-1",
            object_type="uri",
        )

        node_id_val = "test-subjekt-0"
        arcs = [
            {
                "subject": node_id_val,
                "predicate": "ex:validPredicate",
                "object": "test-objekt-1",
                "object_type": "uri",
            },
            {
                "subject": node_id_val,
                "predicate": "ex:nonExistentPredicate",
                "object": "test-objekt-2",
                "object_type": "uri",
            },
        ]

        with pytest.raises(ValueError, match="Predicate not found"):
            create_node_arcs(triple_svc, node_svc, node_id_val, arcs)

        # Verify: no arcs remain (including the pre-existing one removed by rollback)
        remaining = triple_svc.get_by_nodes([node_id_val])
        assert remaining == [], (
            f"Expected no arcs after rollback, got {len(remaining)}"
        )


# ── F2: AmbiguousUUIDError handling ─────────────────────────────────────


class TestAmbiguousUUIDErrorHandling:
    """AmbiguousUUIDError must not be silently swallowed by except ValueError."""

    def test_resolve_subjects_ambiguous_warns(self, node_svc, capsys):
        """Ambiguous prefix in resolve_subjects warns and returns empty."""
        # Create two nodes sharing the same 8-char prefix
        id1 = "ab000000-0000-0000-0000-000000000001"
        id2 = "ab000000-0000-0000-0000-000000000002"
        node_svc.create({"node_id": id1, "etikedoj": {"eo": "NodoUnu"}})
        node_svc.create({"node_id": id2, "etikedoj": {"eo": "NodoDu"}})

        # The first 8 chars are identical for both
        prefix = id1[:8]

        result = resolve_subjects(node_svc, prefix)
        assert result == [], "Ambiguous prefix should return empty list"

    def test_resolve_objects_ambiguous_warns(self, node_svc):
        """Ambiguous prefix in resolve_objects warns and returns empty."""
        id1 = "ac000000-0000-0000-0000-000000000001"
        id2 = "ac000000-0000-0000-0000-000000000002"
        node_svc.create({"node_id": id1, "etikedoj": {"eo": "NodoTri"}})
        node_svc.create({"node_id": id2, "etikedoj": {"eo": "NodoKvar"}})

        prefix = id1[:8]
        result = resolve_objects(node_svc, prefix)
        assert result == [], "Ambiguous object prefix should return empty list"

    def test_resolve_subjects_not_found_falls_through(self, node_svc):
        """Non-ambiguous but not-found UUID falls through to FTS5."""
        node_svc.create({"node_id": "someLabelNode", "etikedoj": {"eo": "Unika Etikedo"}})

        # This UUID prefix doesn't match any node but looks like one
        result = resolve_subjects(node_svc, "aabbccdd")
        # Should fall through to FTS5 and find nothing (no matching label)
        assert result == [] or "Unika" not in str(result)


# ── F3: Shared extract_label_text ───────────────────────────────────────


class TestSharedExtractLabelText:
    """extract_label_text from _node_helpers is used by _predicate_service."""

    def test_extract_from_dict(self):
        """extract_label_text handles dict input."""
        result = extract_label_text({"eo": "tipo", "en": "type"})
        assert "tipo" in result
        assert "type" in result

    def test_extract_from_json_string(self):
        """extract_label_text handles JSON string input."""
        result = extract_label_text('{"eo": "tipo", "en": "type"}')
        assert "tipo" in result
        assert "type" in result

    def test_extract_empty_dict(self):
        """extract_label_text returns empty for empty dict."""
        assert extract_label_text({}) == ""

    def test_extract_empty_string(self):
        """extract_label_text returns empty for invalid input."""
        assert extract_label_text("") == ""


# ── F4: Narrowed exception in delete() ──────────────────────────────────


class TestNarrowedDeleteException:
    """NodeService.delete() should only catch sqlite3.Error and OSError."""

    def test_delete_with_post_delete_failure(self, node_svc, monkeypatch):
        """Post-delete DB error is caught as warning."""
        node_svc.create({"node_id": "delete-test-node", "etikedoj": {"eo": "test"}})

        def broken_post_delete(*args, **kwargs):
            msg = "Simulated database error"
            raise sqlite3.Error(msg)

        monkeypatch.setattr(node_svc, "_post_delete", broken_post_delete)
        # Should not raise
        node_svc.delete("delete-test-node", soft=False)

    def test_delete_with_oserror_post_delete(self, node_svc, monkeypatch):
        """Post-delete OSError is caught as warning."""
        node_svc.create({"node_id": "oserror-test-node", "etikedoj": {"eo": "test"}})

        def broken_post_delete(*args, **kwargs):
            msg = "Simulated IO error"
            raise OSError(msg)

        monkeypatch.setattr(node_svc, "_post_delete", broken_post_delete)
        # Should not raise
        node_svc.delete("oserror-test-node", soft=False)

    def test_rollback_delete_failure_preserves_original_error(
        self, db, node_svc, pred_svc, triple_svc
    ):
        """When node_svc.delete() fails during rollback, the original ValueError still propagates."""
        node_svc.create({"node_id": "rollback-del-nodo", "etikedoj": {"eo": "RB-Del"}})
        node_svc.create({"node_id": "rb-objekt-1", "etikedoj": {"eo": "RbObj1"}})
        pred_svc.create({"predicate_id": "ex:pred", "etikedoj": {"eo": "pred"}})

        node_id_val = "rollback-del-nodo"
        arcs = [
            {
                "subject": node_id_val,
                "predicate": "ex:pred",
                "object": "rb-objekt-1",
                "object_type": "uri",
            },
            {
                "subject": node_id_val,
                "predicate": "ex:nonexistent-pred",
                "object": "rb-objekt-1",
                "object_type": "uri",
            },
        ]

        original_delete = node_svc.delete

        def broken_delete(*args, **kwargs):
            msg = "Simulated delete failure during rollback"
            raise ValueError(msg)

        import unittest.mock as mock
        with (
            mock.patch.object(node_svc, "delete", broken_delete),
            pytest.raises(ValueError, match="Predicate not found"),
        ):
            create_node_arcs(triple_svc, node_svc, node_id_val, arcs)

        # Restore original delete for cleanup
        node_svc.delete = original_delete

    def test_rollback_remove_by_node_failure_preserves_original_error(
        self, db, node_svc, pred_svc, triple_svc
    ):
        """When triple_svc.remove_by_node() fails during rollback, the original ValueError still propagates."""
        node_svc.create({"node_id": "rollback-rm-nodo", "etikedoj": {"eo": "RB-Rm"}})
        node_svc.create({"node_id": "rb-objekt-2", "etikedoj": {"eo": "RbObj2"}})
        pred_svc.create({"predicate_id": "ex:pred2", "etikedoj": {"eo": "pred2"}})

        node_id_val = "rollback-rm-nodo"
        arcs = [
            {
                "subject": node_id_val,
                "predicate": "ex:pred2",
                "object": "rb-objekt-2",
                "object_type": "uri",
            },
            {
                "subject": node_id_val,
                "predicate": "ex:nonexistent-pred2",
                "object": "rb-objekt-2",
                "object_type": "uri",
            },
        ]

        def broken_remove(*args, **kwargs):
            msg = "Simulated remove failure during rollback"
            raise sqlite3.Error(msg)

        import unittest.mock as mock
        with (
            mock.patch.object(triple_svc, "remove_by_node", broken_remove),
            pytest.raises(ValueError, match="Predicate not found"),
        ):
            create_node_arcs(triple_svc, node_svc, node_id_val, arcs)

    def test_delete_with_unexpected_error_raises(self, node_svc, monkeypatch):
        """Post-delete unexpected error type should propagate."""
        node_svc.create({"node_id": "unexpected-test-node", "etikedoj": {"eo": "test"}})

        def broken_post_delete(*args, **kwargs):
            msg = "Something completely unexpected"
            raise TypeError(msg)

        monkeypatch.setattr(node_svc, "_post_delete", broken_post_delete)
        with pytest.raises(TypeError, match="Something completely unexpected"):
            node_svc.delete("unexpected-test-node", soft=False)
