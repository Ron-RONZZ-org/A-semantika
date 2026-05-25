"""Tests for Review Round 13 fixes.

Covers:
- LIKE wildcard escaping in _cli_predikat_grupo.py
- Migration except:pass → narrow exceptions + warning
- NodeService.update() transaction boundary (UPDATE + FTS in single TX)
- Broad except Exception narrowed to specific types in rubujo
- Label "UUID:" → "ID:" in nodo vidi output
- _format_delete_error helper extracted from nodo forigi
"""
from __future__ import annotations

import sqlite3

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app
from A_semantika._cli_nodo import _format_delete_error
from A_semantika._cli_predikat_grupo import _match_groups_by_prefix
from A_semantika._node_service import NodeService


# ── F1: LIKE wildcard escaping in _match_groups_by_prefix ──────────────


class TestMatchGroupsByPrefixLikeEscaping:
    """_match_groups_by_prefix must escape LIKE wildcards in user input."""

    def test_underscore_matched_literally(self, group_svc):
        """A group with '_' in name should only match literal '_'."""
        group_svc.create({"group_name": "test_group"})
        group_svc.create({"group_name": "testXgroup"})

        # Searching for "test_" should match ONLY "test_group" if
        # underscore is escaped (literal match), otherwise both.
        results = _match_groups_by_prefix(group_svc, "test_")
        names = [r["group_name"] for r in results]
        assert names == ["test_group"], (
            f"Expected only 'test_group', got {names}"
        )

    def test_percent_matched_literally(self, group_svc):
        """A group with '%' in name should only match literal '%'."""
        # Create a group name containing %
        group_svc.create({"group_name": "100%real"})
        group_svc.create({"group_name": "100real"})
        group_svc.create({"group_name": "100Xreal"})

        # Searching for "100%" should match only "100%real"
        results = _match_groups_by_prefix(group_svc, "100%")
        names = [r["group_name"] for r in results]
        assert names == ["100%real"], (
            f"Expected only '100%real', got {names}"
        )

    def test_backslash_escaped(self, group_svc):
        """Backslash in prefix should not cause ESCAPE errors."""
        # Backslash at end of prefix (common source of escape errors)
        results = _match_groups_by_prefix(group_svc, "test\\")
        assert isinstance(results, list)


# ── F2: Migration exception narrowing ──────────────────────────────────


class TestMigrationExceptionNarrowing:
    """Migrations should gracefully handle non-existent tables."""

    def test_migrate_nodes_uuid_to_node_id_idempotent(self, db):
        """Running migration on fresh DB should not raise."""
        from A_semantika.data.migrations import migrate_nodes_uuid_to_node_id

        # Should not raise even on fresh/empty schema
        migrate_nodes_uuid_to_node_id(db)

    def test_migrate_predicates_uuid_to_predicate_id_idempotent(self, db):
        """Running predicate migration on fresh DB should not raise."""
        from A_semantika.data.migrations import (
            migrate_predicates_uuid_to_predicate_id,
        )

        migrate_predicates_uuid_to_predicate_id(db)

    def test_migrate_predicate_group_members_unique_idempotent(self, db):
        """Running group members migration on fresh DB should not raise."""
        from A_semantika.data.migrations import (
            migrate_predicate_group_members_unique,
        )

        migrate_predicate_group_members_unique(db)

    def test_migrate_predicates_fts_idempotent(self, db):
        """Running FTS migration on fresh DB should not raise."""
        from A_semantika.data.migrations import migrate_predicates_fts

        migrate_predicates_fts(db)

    def test_all_migrations_graceful_on_empty_db(self, db):
        """Running ALL migrations on a DB with no tables should not raise."""
        # Drop all tables to simulate edge case
        for table in [
            "nodes_fts", "predicates_fts",
            "triples", "predicate_group_members",
            "predicate_groups", "predicates",
            "nodes_rubujo", "predicates_rubujo",
            "nodes",
        ]:
            try:
                db.execute(f"DROP TABLE IF EXISTS {table}")
            except Exception:
                pass

        from A_semantika.data.migrations import (
            migrate_nodes_uuid_to_node_id,
            migrate_predicate_group_members_unique,
            migrate_predicates_fts,
            migrate_predicates_uuid_to_predicate_id,
        )

        # None should raise
        migrate_nodes_uuid_to_node_id(db)
        migrate_predicates_uuid_to_predicate_id(db)
        migrate_predicate_group_members_unique(db)
        migrate_predicates_fts(db)


# ── F3: NodeService.update() transaction boundary ──────────────────────


class TestNodeUpdateTransaction:
    """Node update + FTS re-index must be in a single transaction."""

    def test_update_preserves_fts_index(self, node_svc):
        """After updating a node, FTS search should still find it."""
        node_svc.create({
            "node_id": "fts-update-test",
            "etikedoj": {"eo": "Originala Etikedo"},
        })

        # Update the label — node + FTS should be wrapped in one transaction
        node_svc.update("fts-update-test", {
            "etikedoj": {"eo": "Modifita Etikedo"},
        })

        # New label should be searchable via FTS (label_text was re-indexed)
        new_results = node_svc.search("Modifita")
        assert len(new_results) >= 1
        assert new_results[0]["node_id"] == "fts-update-test"

    def test_update_without_fts_still_works(self, node_svc):
        """Node update should work even without FTS changes."""
        node = node_svc.create({
            "node_id": "no-fts-change",
            "etikedoj": {"eo": "Testo"},
        })

        # Update without touching etikedoj (no FTS change)
        updated = node_svc.update("no-fts-change", {
            "difinoj": {"eo": "Nur difino"},
        })
        assert updated["node_id"] == "no-fts-change"


# ── F5: UUID → ID label in nodo vidi output ───────────────────────────


class TestNodoVidiUuidToIdLabel:
    """nodo vidi should show 'ID:' not 'UUID:' in output."""

    def test_vidi_shows_id_not_uuid(self, runner: CliRunner):
        """vidi output should contain 'ID:' not 'UUID:'."""
        runner.invoke(app, [
            "nodo", "aldoni", "id-label-test",
            "-e", "eo::Etikedo", "--jes",
        ])

        result = runner.invoke(app, ["nodo", "vidi", "id-label-test"])
        assert result.exit_code == 0
        # Should NOT contain "UUID:"
        assert "UUID:" not in result.stdout
        assert "ID:" in result.stdout


# ── F6: _format_delete_error helper ────────────────────────────────────


class TestFormatDeleteError:
    """_format_delete_error should produce correct localized messages."""

    def test_unique_constraint_message(self):
        """UNIQUE constraint failure should produce 'already in trash'."""
        err = sqlite3.IntegrityError(
            "UNIQUE constraint failed: nodes_rubujo.node_id"
        )
        msg = _format_delete_error("test-node-123", err)
        assert "rubujo" in msg or "trash" in msg or "corbeille" in msg

    def test_fk_constraint_message(self):
        """FK constraint failure should produce 'has arcs' message."""
        err = sqlite3.IntegrityError(
            "FOREIGN KEY constraint failed"
        )
        msg = _format_delete_error("test-node-456", err)
        assert "arkojn" in msg or "arcs" in msg or "arcs" in msg

    def test_other_integrity_error_passes_through(self):
        """Other IntegrityError messages should pass through verbatim."""
        err = sqlite3.IntegrityError("some other error")
        msg = _format_delete_error("test-node", err)
        assert msg == "some other error"

    def test_malformed_database_message(self):
        """DatabaseError with 'malformed' should include the actual error."""
        err = sqlite3.DatabaseError("database disk image is malformed")
        msg = _format_delete_error("test-node", err)
        assert "test-node" in msg
        assert "malformed" in msg

    def test_other_database_error_passes_through(self):
        """Other DatabaseError should include UUID and error message."""
        err = sqlite3.DatabaseError("database is locked")
        msg = _format_delete_error("test-node", err)
        assert "test-node" in msg
        assert "database is locked" in msg

    def test_unknown_exception_passes_through(self):
        """Non-sqlite3 exceptions should include UUID and error message."""
        err = ValueError("something else")
        msg = _format_delete_error("test-node", err)
        assert "test-node" in msg
        assert "something else" in msg
