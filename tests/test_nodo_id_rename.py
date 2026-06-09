"""Tests for NodeService.update_node_id() and nodo modifi --nova-id."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app


class TestNodoRenameService:
    """Unit tests for NodeService.update_node_id()."""

    def test_rename_node_id_only(self, node_svc):
        """Rename a node with no triples, verify FTS updated."""
        node_svc.create({"node_id": "OLDID", "etikedoj": {"eo": "Malnova"}})
        updated = node_svc.update_node_id("OLDID", "NEWID", {})
        assert updated["node_id"] == "NEWID"
        # FTS should find it under new ID
        results = node_svc.search("Malnova", limit=1)
        assert len(results) >= 1
        assert results[0]["node_id"] == "NEWID"
        # Old ID should not exist
        assert node_svc.get("OLDID") is None

    def test_rename_node_with_triples(self, node_svc, pred_svc, triple_svc):
        """Rename a node that is a subject and URI object of triples."""
        pred_svc.create({"predicate_id": "test:rel", "etikedoj": {"eo": "rilato"}})
        node_svc.create({"node_id": "SUBJ", "etikedoj": {"eo": "Subjekto"}})
        node_svc.create({"node_id": "OBJ", "etikedoj": {"eo": "Objekto"}})
        triple_svc.add("SUBJ", "test:rel", "OBJ", object_type="uri")
        triple_svc.add("OBJ", "test:rel", "SUBJ", object_type="uri")

        # Rename SUBJ → NEWSUBJ
        node_svc.update_node_id("SUBJ", "NEWSUBJ", {})
        # Triple subject should be updated
        triples = triple_svc.get_by_subject("NEWSUBJ")
        assert len(triples) == 1
        assert triples[0]["object_value"] == "OBJ"
        # Triple where SUBJ was URI object should also be updated
        obj_triples = triple_svc.get_by_object("NEWSUBJ")
        assert len(obj_triples) == 1
        assert obj_triples[0]["subject_uuid"] == "OBJ"

    def test_rename_node_with_labels(self, node_svc):
        """Rename + update labels simultaneously."""
        node_svc.create({"node_id": "OLD", "etikedoj": {"eo": "Malnova"}})
        updated = node_svc.update_node_id("OLD", "NEW", {"etikedoj": {"eo": "Nova"}})
        assert updated["node_id"] == "NEW"
        assert json.loads(updated["etikedoj"]) == {"eo": "Nova"}

    def test_rename_nonexistent_node(self, node_svc):
        """Renaming a non-existent node raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            node_svc.update_node_id("GHOST", "NEW", {})

    def test_rename_to_existing_id(self, node_svc):
        """Renaming to an existing node_id raises ValueError."""
        node_svc.create({"node_id": "EXISTING", "etikedoj": {"eo": "Ekzistanta"}})
        node_svc.create({"node_id": "SOURCE", "etikedoj": {"eo": "Fonto"}})
        with pytest.raises(ValueError, match="already exists"):
            node_svc.update_node_id("SOURCE", "EXISTING", {})

    def test_rename_to_existing_caught_by_precheck(self, node_svc, pred_svc, triple_svc):
        """Renaming to an existing node_id is caught by the 'already exists'
        pre-check before reaching PK collision checks. PK collision cannot
        occur independently because FK constraints prevent triples from
        referencing a non-existent subject_uuid or object_value."""
        pred_svc.create({"predicate_id": "test:rel2", "etikedoj": {"eo": "rilato"}})
        node_svc.create({"node_id": "A", "etikedoj": {"eo": "Node A"}})
        node_svc.create({"node_id": "B", "etikedoj": {"eo": "Node B"}})
        triple_svc.add("A", "test:rel2", "B", object_type="uri")
        with pytest.raises(ValueError, match="already exists"):
            node_svc.update_node_id("B", "A", {})

    def test_generated_column_auto_recompute(self, node_svc, pred_svc, triple_svc):
        """object_node_uuid should auto-recompute after rename."""
        pred_svc.create({"predicate_id": "test:rel4", "etikedoj": {"eo": "rilato"}})
        node_svc.create({"node_id": "SUBJ1", "etikedoj": {"eo": "S1"}})
        node_svc.create({"node_id": "OBJ1", "etikedoj": {"eo": "O1"}})
        triple_svc.add("SUBJ1", "test:rel4", "OBJ1", object_type="uri")

        # Rename OBJ1 → NEWOBJ
        node_svc.update_node_id("OBJ1", "NEWOBJ", {})

        # Read triple directly to check generated column
        triples = node_svc.db.execute(
            "SELECT object_node_uuid FROM triples WHERE subject_uuid = ? AND predicate_id = ?",
            ("SUBJ1", "test:rel4"),
        )
        assert len(triples) == 1
        assert triples[0]["object_node_uuid"] == "NEWOBJ"


class TestNodoRenameCLI:
    """CLI integration tests for nodo modifi --nova-id."""

    def test_cli_rename_node(self, runner: CliRunner, node_svc):
        """nod modifi --nova-id should rename the node."""
        node_svc.create({"node_id": "OLDID", "etikedoj": {"eo": "Nodo"}})
        result = runner.invoke(app, [
            "nodo", "modifi", "OLDID", "--nova-id", "NEWID", "-y",
        ])
        assert result.exit_code == 0
        assert "renomita" in result.stdout or "renamed" in result.stdout
        assert "OLDID" in result.stdout
        assert "NEWID" in result.stdout
        assert node_svc.get("OLDID") is None
        assert node_svc.get("NEWID") is not None

    def test_cli_rename_collision(self, runner: CliRunner, node_svc):
        """nod modifi --nova-id with existing ID shows error."""
        node_svc.create({"node_id": "A", "etikedoj": {"eo": "Node A"}})
        node_svc.create({"node_id": "B", "etikedoj": {"eo": "Node B"}})
        result = runner.invoke(app, [
            "nodo", "modifi", "A", "--nova-id", "B", "-y",
        ])
        assert result.exit_code == 1
        # Error goes to stderr via error()
        assert "already exists" in result.stdout or "already exists" in result.stderr

    def test_cli_rename_noop(self, runner: CliRunner, node_svc):
        """--nova-id same as current ID should be treated as no-op if no other changes."""
        node_svc.create({"node_id": "SAME", "etikedoj": {"eo": "Nodo"}})
        result = runner.invoke(app, [
            "nodo", "modifi", "SAME", "--nova-id", "SAME", "-y",
        ])
        assert result.exit_code == 1
        assert "Neniu ŝanĝo" in result.stdout or "No change" in result.stdout

    def test_cli_rename_preview_shows_id_change(self, runner: CliRunner, node_svc):
        """Interactive rename should show ID change in preview table."""
        node_svc.create({"node_id": "OLDID", "etikedoj": {"eo": "Nodo"}})
        result = runner.invoke(app, [
            "nodo", "modifi", "OLDID", "--nova-id", "NEWID",
        ], input="\n")  # accept default confirmation
        assert result.exit_code == 0
        assert "OLDID" in result.stdout
        assert "NEWID" in result.stdout
        assert "ID" in result.stdout  # ID field row shown

    def test_cli_rename_preview_shows_without_labels(self, runner: CliRunner, node_svc):
        """Rename preview shows ID change even without label changes."""
        node_svc.create({"node_id": "LONG_NODE_ID_OLD", "etikedoj": {"eo": "Nodo"}})
        result = runner.invoke(app, [
            "nodo", "modifi", "LONG_NODE_ID_OLD", "--nova-id", "NEW_ID",
        ], input="\n")
        assert result.exit_code == 0
        assert "LONG_NODE" in result.stdout  # truncated old ID in preview
        assert "NEW_ID" in result.stdout

    def test_cli_rename_nonexistent(self, runner: CliRunner):
        """Renaming a non-existent node shows error."""
        result = runner.invoke(app, [
            "nodo", "modifi", "GHOST", "--nova-id", "NEW", "-y",
        ])
        assert result.exit_code == 1
        assert "ne trovita" in result.stdout or "not found" in result.stdout



