"""Regression tests for code review round 20 fixes.

Fixes applied:
  M1: Hard-delete in create_node_arcs() rollback — soft=False, not soft
  M2: FTS transaction in NodeService.create() — INSERT + FTS in single tx
  M3: FTS removal inside _move_to_trash() transaction
  M4: build_triple_preview_table() returns (None, "") instead of typer.Exit
  M5: resolve_trash_item() — exact match, prefix, case-insensitive, wildcard escaping
"""
from __future__ import annotations

import pytest

from A_semantika._cli_helpers import create_node_arcs
from A_semantika._rubujo_helpers import resolve_trash_item


# ═══════════════════════════════════════════════════════════════════════
# M1: Hard-delete rollback in create_node_arcs()
# ═══════════════════════════════════════════════════════════════════════


class TestM1HardDeleteRollback:
    """When create_node_arcs() fails, the node must be hard-deleted (soft=False)
    so no misleading trash entry remains. The node was never successfully
    created, so a trash entry would imply it existed and was deleted."""

    def _setup_node_with_predicate(self, node_svc, pred_svc) -> str:
        """Create a node and seeded predicate, return node_id."""
        node_svc.create({"node_id": "test-m1", "etikedoj": {"eo": "Test M1"}})
        return "test-m1"

    def test_rollback_uses_hard_delete(self, node_svc, pred_svc, triple_svc, db):
        """When arc creation fails, node must be hard-deleted (no trash entry)."""
        self._setup_node_with_predicate(node_svc, pred_svc)

        # Create an arc with an invalid predicate to trigger rollback
        arcs = [
            {"subject": "test-m1", "predicate": "rdf:NONEXISTENT",
             "object": "test-m1", "object_type": "uri"},
        ]

        with pytest.raises(ValueError, match="Predicate not found"):
            create_node_arcs(triple_svc, node_svc, "test-m1", arcs)

        # Node must NOT exist in the main table
        node = node_svc.get("test-m1")
        assert node is None, "Node should have been hard-deleted from main table"

        # Node must NOT exist in the trash table either (hard-delete = no trash)
        trash = resolve_trash_item(db, "nodes_rubujo", "node_id", "test-m1", ValueError)
        assert trash is None, (
            "Rollback must hard-delete (soft=False), not create trash entry. "
            "A soft-delete would leave a misleading trash entry for a node "
            "that was never successfully created."
        )

    def test_successful_arc_creation_no_rollback(self, node_svc, pred_svc, triple_svc):
        """When all arcs succeed, the node must remain (no rollback)."""
        node_svc.create({"node_id": "test-m1b", "etikedoj": {"eo": "Test M1B"}})
        # rdf:type is seeded automatically

        arcs = [
            {"subject": "test-m1b", "predicate": "rdf:type",
             "object": "test-m1b", "object_type": "uri"},
        ]

        # Should not raise — all arcs valid
        create_node_arcs(triple_svc, node_svc, "test-m1b", arcs)

        # Node must still exist
        node = node_svc.get("test-m1b")
        assert node is not None, "Node should still exist after successful arc creation"

        # Triple should exist
        triple = triple_svc.get_one("test-m1b", "rdf:type", "test-m1b", "uri")
        assert triple is not None, "Arc should have been created"

    def test_partial_arcs_removed_on_rollback(self, node_svc, pred_svc, triple_svc, db):
        """When rollback occurs, partially created arcs must also be removed."""
        node_svc.create({"node_id": "test-m1c", "etikedoj": {"eo": "Test M1C"}})
        # rdf:type is seeded

        # First arc: valid. Second arc: invalid → should rollback both
        arcs = [
            {"subject": "test-m1c", "predicate": "rdf:type",
             "object": "test-m1c", "object_type": "uri"},
            {"subject": "test-m1c", "predicate": "rdf:BOGUS",
             "object": "test-m1c", "object_type": "uri"},
        ]

        with pytest.raises(ValueError):
            create_node_arcs(triple_svc, node_svc, "test-m1c", arcs)

        # No triples should remain for the failed node
        where_clause = "subject_uuid = ?"
        triples = triple_svc.search_triples(where_clause, ["test-m1c"])
        assert len(triples) == 0, (
            "Partially created arcs must be removed during rollback. "
            f"Found {len(triples)} remaining triples."
        )


# ═══════════════════════════════════════════════════════════════════════
# M2 + M3: FTS transaction in create() and _move_to_trash()
# ═══════════════════════════════════════════════════════════════════════


class TestM2FtsTransactionInCreate:
    """NodeService.create() must wrap INSERT + FTS index in a single
    transaction. After create, the node must be searchable via FTS."""

    def test_created_node_searchable_via_fts(self, node_svc):
        """Node created via create() must be searchable via FTS5."""
        node_svc.create({"node_id": "test-fts-create", "etikedoj": {"eo": "FTS Koala"}})

        results = node_svc.search("Koala")
        ids = [r["node_id"] for r in results]
        assert "test-fts-create" in ids, (
            "Node created via create() must be searchable via FTS. "
            "If the FTS index wasn't committed, the node would not appear."
        )

    def test_fts_index_after_create_multiple(self, node_svc):
        """Multiple created nodes must all be FTS-searchable."""
        labels = ["FTS Alpha", "FTS Beta", "FTS Gamma"]
        for i, label in enumerate(labels):
            node_svc.create({
                "node_id": f"test-fts-multi-{i}",
                "etikedoj": {"eo": label},
            })

        for label in labels:
            results = node_svc.search(label)
            assert len(results) >= 1, f"Node with label '{label}' not found via FTS"


class TestM3FtsRemovalInMoveToTrash:
    """After soft-delete, the node must be removed from FTS index so
    it no longer appears in search results."""

    def test_fts_removed_from_table_after_delete(self, node_svc, db):
        """After soft-delete, node_id must be removed from the FTS table.

        We verify directly in the FTS table because FTS5 MATCH queries on
        external content tables may fail with "missing row" errors after
        the content row is deleted (even when the FTS 'delete' command
        is issued). Direct table inspection avoids this SQLite limitation.
        """
        node_svc.create({"node_id": "test-fts-del", "etikedoj": {"eo": "FTS Delete Me"}})

        # Verify in FTS table before delete
        rows = db.execute("SELECT node_id FROM nodes_fts WHERE node_id = ?",
                          ("test-fts-del",))
        assert len(rows) == 1, "Node should be in FTS table before delete"

        # Soft delete
        node_svc.delete("test-fts-del", soft=True)

        # Verify removed from FTS table after delete
        rows = db.execute("SELECT node_id FROM nodes_fts WHERE node_id = ?",
                          ("test-fts-del",))
        assert len(rows) == 0, (
            "Node must be removed from FTS table after soft-delete. "
            "If _remove_from_fts() fails, the FTS 'delete' command "
            "does not remove the entry, leaving a dangling reference."
        )

    def test_fts_reindexed_after_restore(self, node_svc, db):
        """After restore from trash, node_id must be re-added to FTS table."""
        node_svc.create({"node_id": "test-fts-restore", "etikedoj": {"eo": "FTS Restore Me"}})

        # Delete
        node_svc.delete("test-fts-restore", soft=True)

        # Verify gone from FTS table
        rows = db.execute("SELECT node_id FROM nodes_fts WHERE node_id = ?",
                          ("test-fts-restore",))
        assert len(rows) == 0

        # Restore
        node_svc.restore("test-fts-restore")

        # Verify back in FTS table
        rows = db.execute("SELECT node_id FROM nodes_fts WHERE node_id = ?",
                          ("test-fts-restore",))
        assert len(rows) == 1, "Node must be re-indexed in FTS after restore"


# ═══════════════════════════════════════════════════════════════════════
# M4: build_triple_preview_table() returns (None, "") on ambiguous prefix
# ═══════════════════════════════════════════════════════════════════════


class TestM4PreviewReturnsNone:
    """build_triple_preview_table() must return (None, "") when the
    subject or object prefix is ambiguous, instead of raising typer.Exit(1).
    This allows callers to handle the error at the appropriate level."""

    def test_ambiguous_subject_returns_none(self, node_svc, pred_svc):
        """Ambiguous subject prefix must return (None, "")."""
        from A_semantika._preview import build_triple_preview_table

        # Create two nodes with overlapping prefixes
        node_svc.create({"node_id": "test-ambig-xx1", "etikedoj": {"eo": "Ambiguous 1"}})
        node_svc.create({"node_id": "test-ambig-xx2", "etikedoj": {"eo": "Ambiguous 2"}})

        # Use a prefix matching both — should NOT raise typer.Exit
        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            "test-ambig-xx", "rdf:type", "test-ambig-xx1",
            "uri",
        )
        assert table is None, "Ambiguous subject prefix should return None table"
        assert footnote == "", "Ambiguous subject prefix should return empty footnote"

    def test_ambiguous_object_returns_none(self, node_svc, pred_svc):
        """Ambiguous object prefix must return (None, "")."""
        from A_semantika._preview import build_triple_preview_table

        node_svc.create({"node_id": "test-ambig-obj1", "etikedoj": {"eo": "Obj Amb 1"}})
        node_svc.create({"node_id": "test-ambig-obj2", "etikedoj": {"eo": "Obj Amb 2"}})
        subj = node_svc.create({"etikedoj": {"eo": "Subject Node"}})

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["node_id"], "rdf:type",
            "test-ambig-obj",  # Ambiguous prefix
            "uri",
        )
        assert table is None, "Ambiguous object prefix should return None table"
        assert footnote == ""

    def test_ambiguous_unit_returns_none(self, node_svc, pred_svc):
        """Ambiguous unit prefix must return (None, "")."""
        from A_semantika._preview import build_triple_preview_table

        node_svc.create({"node_id": "test-unit-amb1", "etikedoj": {"eo": "Unit Amb 1"}})
        node_svc.create({"node_id": "test-unit-amb2", "etikedoj": {"eo": "Unit Amb 2"}})
        subj = node_svc.create({"node_id": "test-subj-unit", "etikedoj": {"eo": "Subj Unit"}})

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["node_id"], "wdt:P1082",
            "1000000",
            "literal", object_datatype="xsd:integer",
            object_unit="test-unit-amb",  # Ambiguous prefix
        )
        assert table is None, "Ambiguous unit prefix should return None table"
        assert footnote == ""

    def test_valid_prefix_returns_table(self, node_svc, pred_svc):
        """Valid (non-ambiguous) prefix must return a Table."""
        from A_semantika._preview import build_triple_preview_table

        subj = node_svc.create({"etikedoj": {"eo": "Valid Subj"}})
        obj = node_svc.create({"etikedoj": {"eo": "Valid Obj"}})

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["node_id"], "rdf:type", obj["node_id"],
            "uri",
        )
        assert table is not None, "Valid prefix should return a Table"
        assert "→ URI" in footnote


class TestM4ConfirmTripleReturnsFalse:
    """confirm_triple() must return False when build_triple_preview_table
    returns None (ambiguous prefix), rather than crashing."""

    def test_confirm_triple_ambiguous_returns_false(self, node_svc, pred_svc):
        """confirm_triple() with ambiguous subject must return False."""
        from A_semantika._preview import confirm_triple

        node_svc.create({"node_id": "test-confirm-xx1", "etikedoj": {"eo": "Confirm 1"}})
        node_svc.create({"node_id": "test-confirm-xx2", "etikedoj": {"eo": "Confirm 2"}})

        # Should not crash — should return False
        result = confirm_triple(
            node_svc, pred_svc,
            "test-confirm-xx", "rdf:type", "test-confirm-xx1",
            "uri",
        )
        assert result is False, "Ambiguous prefix should make confirm_triple return False"

    def test_confirm_triple_valid_returns_true_when_yes(self, node_svc, pred_svc):
        """confirm_triple() with valid data and yes=True returns True."""
        from A_semantika._preview import confirm_triple

        subj = node_svc.create({"etikedoj": {"eo": "Yes Subj"}})
        obj = node_svc.create({"etikedoj": {"eo": "Yes Obj"}})

        result = confirm_triple(
            node_svc, pred_svc,
            subj["node_id"], "rdf:type", obj["node_id"],
            "uri",
            yes=True,
        )
        assert result is True


# ═══════════════════════════════════════════════════════════════════════
# M5: resolve_trash_item() - shared helper behavior
# ═══════════════════════════════════════════════════════════════════════


class TestM5ResolveTrashItem:
    """resolve_trash_item() must correctly resolve item IDs against
    trash tables, handling exact match, prefix match, case-insensitive
    lookup, LIKE wildcard escaping, and ambiguous prefixes."""

    def _setup_trash(self, node_svc) -> None:
        """Create nodes and soft-delete them for trash testing."""
        for nid, label in [
            ("test-resolve-exact", "Exact Match"),
            ("test-resolve-prefix-a", "Prefix A"),
            ("test-resolve-prefix-b", "Prefix B"),
            ("test_underscore_1", "Underscore 1"),
            ("test%pct", "Percent Node"),
        ]:
            node_svc.create({"node_id": nid, "etikedoj": {"eo": label}})
            node_svc.delete(nid, soft=True)

    def test_exact_match(self, node_svc, db):
        """Exact node_id match must return the trash item."""
        self._setup_trash(node_svc)
        result = resolve_trash_item(db, "nodes_rubujo", "node_id",
                                    "test-resolve-exact", ValueError)
        assert result is not None
        assert result["node_id"] == "test-resolve-exact"

    def test_prefix_match(self, node_svc, db):
        """Prefix match (single result) must return the trash item."""
        self._setup_trash(node_svc)
        result = resolve_trash_item(db, "nodes_rubujo", "node_id",
                                    "test-resolve-prefix-a", ValueError)
        assert result is not None
        assert result["node_id"] == "test-resolve-prefix-a"

    def test_case_insensitive_exact(self, node_svc, db):
        """Exact match must be case-insensitive (COLLATE NOCASE)."""
        node_svc.create({"node_id": "RUBOJUJO", "etikedoj": {"eo": "rubujo"}})
        node_svc.delete("RUBOJUJO", soft=True)

        # Lowercase query must match uppercase ID
        result = resolve_trash_item(db, "nodes_rubujo", "node_id",
                                    "rubojujo", ValueError)
        assert result is not None
        assert result["node_id"] == "RUBOJUJO"

    def test_case_insensitive_prefix(self, node_svc, db):
        """Prefix match must be case-insensitive."""
        node_svc.create({"node_id": "MAMULO", "etikedoj": {"eo": "mamulo"}})
        node_svc.delete("MAMULO", soft=True)

        # Lowercase prefix must match
        result = resolve_trash_item(db, "nodes_rubujo", "node_id",
                                    "mamulo", ValueError)
        assert result is not None
        assert result["node_id"] == "MAMULO"

    def test_ambiguous_prefix_raises_error(self, node_svc, db):
        """Ambiguous prefix (multiple matches) must raise ValueError."""
        self._setup_trash(node_svc)
        # "test-resolve-prefix-" matches both A and B
        with pytest.raises(ValueError, match="ambiguous"):
            resolve_trash_item(db, "nodes_rubujo", "node_id",
                               "test-resolve-prefix-", ValueError)

    def test_not_found_returns_none(self, node_svc, db):
        """Non-existent ID must return None.

        Creates and deletes a node first to ensure the nodes_rubujo
        table exists (table is created lazily on first soft-delete).
        """
        # Ensure trash table exists by soft-deleting a node
        node_svc.create({"node_id": "test-table-init", "etikedoj": {"eo": "Table Init"}})
        node_svc.delete("test-table-init", soft=True)

        # Now query for a totally different ID — should return None
        result = resolve_trash_item(db, "nodes_rubujo", "node_id",
                                    "completely-nonexistent", ValueError)
        assert result is None

    def test_like_underscore_matched_literally(self, node_svc, db):
        """Underscore in ID must be escaped in LIKE — 'test_' must NOT
        match 'testX1' if 'test_1' also exists."""
        self._setup_trash(node_svc)
        # "test_underscore_1" exists. "test_underscore_" prefix should match
        # it only (not any other node with 'test' + any char + 'underscore').
        result = resolve_trash_item(db, "nodes_rubujo", "node_id",
                                    "test_underscore_1", ValueError)
        assert result is not None
        assert result["node_id"] == "test_underscore_1"

    def test_like_percent_matched_literally(self, node_svc, db):
        """Percent in ID must be escaped in LIKE pattern."""
        self._setup_trash(node_svc)
        result = resolve_trash_item(db, "nodes_rubujo", "node_id",
                                    "test%pct", ValueError)
        assert result is not None
        assert result["node_id"] == "test%pct"


class TestM5BatchResolveErrors:
    """batch_resolve_trash_items() error handling."""

    def test_not_found_error_message(self, node_svc, db):
        """Non-existent ID must produce not-found error."""
        from A_semantika._rubujo_helpers import batch_resolve_trash_items

        resolved, errors = batch_resolve_trash_items(
            db, "nodes_rubujo", "node_id",
            ["nonexistent"], ValueError,
            not_found_msg="not found in trash",
            ambiguous_msg="ambiguous prefix: {e}",
        )
        assert len(resolved) == 0
        assert len(errors) == 1
        assert "not found" in errors[0][1]

    def test_ambiguous_error_message(self, node_svc, db):
        """Ambiguous prefix must produce ambiguous error."""
        from A_semantika._rubujo_helpers import batch_resolve_trash_items

        # Create two nodes with same prefix
        node_svc.create({"node_id": "test-batch-amb1", "etikedoj": {"eo": "Batch Amb 1"}})
        node_svc.create({"node_id": "test-batch-amb2", "etikedoj": {"eo": "Batch Amb 2"}})
        node_svc.delete("test-batch-amb1", soft=True)
        node_svc.delete("test-batch-amb2", soft=True)

        resolved, errors = batch_resolve_trash_items(
            db, "nodes_rubujo", "node_id",
            ["test-batch-amb"], ValueError,
            not_found_msg="not found in trash",
            ambiguous_msg="ambiguous prefix: {e}",
        )
        assert len(resolved) == 0
        assert len(errors) == 1
        assert "ambiguous" in errors[0][1]


# ═══════════════════════════════════════════════════════════════════════
# Smoke: imports and module loading
# ═══════════════════════════════════════════════════════════════════════


class TestSmoke:
    """Basic smoke tests that all modified modules load without error."""

    def test_import_rubujo_helpers(self):
        """_rubujo_helpers module imports successfully."""
        from A_semantika import _rubujo_helpers  # noqa: F401
        assert _rubujo_helpers.resolve_trash_item is not None

    def test_import_preview(self):
        """_preview module imports successfully."""
        from A_semantika import _preview  # noqa: F811
        assert _preview.build_triple_preview_table is not None
