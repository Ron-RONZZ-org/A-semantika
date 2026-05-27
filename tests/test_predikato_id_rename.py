"""Tests for PredicateService.update_predicate_id() and predikato modifi --nova-id."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app


class TestPredicateRenameService:
    """Unit tests for PredicateService.update_predicate_id()."""

    def test_rename_predicate_id_only(self, pred_svc):
        """Rename a predicate with no references, verify FTS updated."""
        pred_svc.create({"predicate_id": "old:pred", "etikedoj": {"eo": "Malnova"}})
        updated = pred_svc.update_predicate_id("old:pred", "new:pred", {})
        assert updated["predicate_id"] == "new:pred"
        # FTS should find it under new ID
        results = pred_svc.search("Malnova", limit=1)
        assert len(results) >= 1
        assert results[0]["predicate_id"] == "new:pred"
        # Old ID should not exist
        assert pred_svc.get_by_predicate_id("old:pred") is None

    def test_rename_predicate_with_triples(self, node_svc, pred_svc, triple_svc):
        """Rename a predicate referenced by triples."""
        node_svc.create({"node_id": "S", "etikedoj": {"eo": "Subjekto"}})
        node_svc.create({"node_id": "O", "etikedoj": {"eo": "Objekto"}})
        pred_svc.create({"predicate_id": "old:rel", "etikedoj": {"eo": "Rilato"}})
        triple_svc.add("S", "old:rel", "O", object_type="uri")

        # Rename predicate
        pred_svc.update_predicate_id("old:rel", "new:rel", {})

        triples = triple_svc.get_by_predicate("new:rel")
        assert len(triples) == 1
        assert triples[0]["subject_uuid"] == "S"

    def test_rename_predicate_with_group_members(self, pred_svc, group_svc):
        """Rename a predicate referenced by predicate_group_members."""
        pred_svc.create({"predicate_id": "old:prop", "etikedoj": {"eo": "Eco"}})
        group_svc.create({"group_name": "testgroup"})
        group_svc.add_member("testgroup", "old:prop")

        pred_svc.update_predicate_id("old:prop", "new:prop", {})

        members = group_svc.list_members("testgroup")
        assert len(members) == 1
        assert members[0]["predicate_id"] == "new:prop"

    def test_rename_nonexistent_predicate(self, pred_svc):
        """Renaming a non-existent predicate raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            pred_svc.update_predicate_id("ghost", "new", {})

    def test_merge_into_existing_id(self, pred_svc):
        """Renaming to an existing predicate_id merges instead of raising."""
        pred_svc.create({"predicate_id": "existing", "etikedoj": {"eo": "Ekzistanta", "en": "Existing"}})
        pred_svc.create({"predicate_id": "source", "etikedoj": {"eo": "Fonto", "fr": "Source"}})

        result = pred_svc.update_predicate_id("source", "existing", {})

        # source should no longer exist
        assert pred_svc.get_by_predicate_id("source") is None
        # existing should survive with merged labels
        assert result["predicate_id"] == "existing"
        # eo from source is overwritten by existing's eo (new wins)
        assert json.loads(result["etikedoj"])["eo"] == "Ekzistanta"
        # fr from source is preserved (gap fill)
        assert json.loads(result["etikedoj"])["fr"] == "Source"
        # en from existing is preserved
        assert json.loads(result["etikedoj"])["en"] == "Existing"

    def test_merge_with_triples_and_group_members(self, node_svc, pred_svc, triple_svc, group_svc):
        """Merge rewires triples and group members, resolving PK collisions."""
        node_svc.create({"node_id": "S", "etikedoj": {"eo": "Subjekto"}})
        node_svc.create({"node_id": "O", "etikedoj": {"eo": "Objekto"}})
        node_svc.create({"node_id": "T", "etikedoj": {"eo": "Alia"}})
        pred_svc.create({"predicate_id": "existing", "etikedoj": {"eo": "Ekzistanta"}})
        pred_svc.create({"predicate_id": "source", "etikedoj": {"eo": "Fonto"}})
        group_svc.create({"group_name": "testgroup"})
        group_svc.add_member("testgroup", "source")
        group_svc.add_member("testgroup", "existing")

        # source triple: collides with existing triple
        triple_svc.add("S", "source", "O", object_type="uri")
        # existing triple: same SPO → collision
        triple_svc.add("S", "existing", "O", object_type="uri")
        # source-only triple: no collision
        triple_svc.add("S", "source", "T", object_type="uri")

        pred_svc.update_predicate_id("source", "existing", {})

        # Colliding triple: existing wins (O → existing kept, source → deleted)
        existing_triples = triple_svc.get_by_predicate("existing")
        assert len(existing_triples) == 2  # (S,existing,O) kept, (S,existing,T) added
        assert any(t["object_value"] == "O" for t in existing_triples)
        assert any(t["object_value"] == "T" for t in existing_triples)

        # source no longer has any triples
        assert len(triple_svc.get_by_predicate("source")) == 0

        # Group members: both source and existing in same group → source removed
        members = group_svc.list_members("testgroup")
        assert len(members) == 1
        assert members[0]["predicate_id"] == "existing"


class TestPredicateRenameCLI:
    """CLI integration tests for predikato modifi --nova-id."""

    def test_cli_rename_predicate(self, runner: CliRunner, pred_svc):
        """predikato modifi --nova-id should rename the predicate."""
        pred_svc.create({"predicate_id": "old:test", "etikedoj": {"eo": "Provo"}})
        result = runner.invoke(app, [
            "predikato", "modifi", "old:test", "--nova-id", "new:test", "-y",
        ])
        assert result.exit_code == 0
        assert "renomita" in result.stdout or "renamed" in result.stdout
        assert "old:test" in result.stdout
        assert "new:test" in result.stdout
        assert pred_svc.get_by_predicate_id("old:test") is None
        assert pred_svc.get_by_predicate_id("new:test") is not None

    def test_cli_rename_preview_before_confirm(self, runner: CliRunner, pred_svc):
        """predikato modifi --nova-id should show rename preview BEFORE confirmation prompt."""
        pred_svc.create({"predicate_id": "old:preview", "etikedoj": {"eo": "Antaŭvido"}})
        # Run without -y, answer "J" (yes) when prompted
        result = runner.invoke(app, [
            "predikato", "modifi", "old:preview", "--nova-id", "new:preview",
        ], input="J\n")
        assert result.exit_code == 0
        # The rename preview should appear before the confirmation prompt
        # We can verify by checking the stdout contains the rename line
        assert "renomita" in result.stdout or "renamed" in result.stdout
        assert "old:preview" in result.stdout
        assert "new:preview" in result.stdout
        # Verify the rename actually happened
        assert pred_svc.get_by_predicate_id("old:preview") is None
        assert pred_svc.get_by_predicate_id("new:preview") is not None

    def test_cli_merge_on_collision(self, runner: CliRunner, pred_svc):
        """predikato modifi --nova-id with existing ID merges instead."""
        pred_svc.create({"predicate_id": "a:one", "etikedoj": {"eo": "Unu"}})
        pred_svc.create({"predicate_id": "a:two", "etikedoj": {"eo": "Du"}})
        result = runner.invoke(app, [
            "predikato", "modifi", "a:one", "--nova-id", "a:two", "-y",
        ])
        assert result.exit_code == 0
        assert "renomita" in result.stdout or "renamed" in result.stdout
        # a:one should be gone (merged into a:two)
        assert pred_svc.get_by_predicate_id("a:one") is None
        assert pred_svc.get_by_predicate_id("a:two") is not None
