"""Tests for Review Round 12 fixes.

Covers:
- Atomic rollback on arc creation failure
- Direct-mode forigi for literal triples
- modifi with both old and new deprecated options
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app
from A_semantika._cli_helpers import create_node_arcs
from A_semantika.data.storage import now


class TestArcAtomicity:
    """Tests for node arc atomicity (_cli_nodo.py:create_node_arcs)."""

    def test_arc_failure_rolls_back_node(self, node_svc, pred_svc, triple_svc):
        """When arc creation fails, the node should be deleted (no orphan)."""
        # Create a target node for the arc
        target = node_svc.create({"node_id": "arc-target-001", "etikedoj": {"eo": "Celo"}})

        # Create the subject node
        subject = node_svc.create({"node_id": "arc-subject-001", "etikedoj": {"eo": "Subjekto"}})

        # Ensure rdf:type predicate exists (seeded by DEFAULT_PREDICATES)
        assert pred_svc.get_by_predicate_id("rdf:type") is not None

        # Build a valid arc
        arcs = [
            {"subject": subject["node_id"], "predicate": "rdf:type",
             "object": target["node_id"], "object_type": "uri"},
        ]

        # create_node_arcs should succeed
        create_node_arcs(triple_svc, node_svc, subject["node_id"], arcs)
        assert node_svc.get(subject["node_id"]) is not None  # Node still exists

    def test_arc_invalid_predicate_rolls_back_node(self, node_svc, pred_svc, triple_svc):
        """When arc creation raises ValueError, the node should be deleted."""
        # Create a target node
        target = node_svc.create({"node_id": "rollback-target-001", "etikedoj": {"eo": "Celo"}})

        # Create the subject node
        subject = node_svc.create({"node_id": "rollback-subject-001", "etikedoj": {"eo": "Subjekto"}})

        # Build an arc with an invalid predicate (doesn't exist)
        arcs = [
            {"subject": subject["node_id"], "predicate": "nonexistent:predicate",
             "object": target["node_id"], "object_type": "uri"},
        ]

        # create_node_arcs should raise ValueError AND delete the node
        with pytest.raises(ValueError, match="Predicate not found"):
            create_node_arcs(triple_svc, node_svc, subject["node_id"], arcs)

        # The node should have been rolled back
        assert node_svc.get(subject["node_id"]) is None

    def test_arc_invalid_object_rolls_back_node(self, node_svc, pred_svc, triple_svc):
        """When arc creation has invalid object, the node should be deleted."""
        # Ensure rdf:type predicate exists
        assert pred_svc.get_by_predicate_id("rdf:type") is not None

        # Create the subject node
        subject = node_svc.create({"node_id": "rollback-subject-002", "etikedoj": {"eo": "Subjekto"}})

        # Build an arc with a URI object that doesn't exist
        arcs = [
            {"subject": subject["node_id"], "predicate": "rdf:type",
             "object": "nonexistent-node-uuid", "object_type": "uri"},
        ]

        # create_node_arcs should raise ValueError AND delete the node
        with pytest.raises(ValueError, match="Object node not found"):
            create_node_arcs(triple_svc, node_svc, subject["node_id"], arcs)

        # The node should have been rolled back
        assert node_svc.get(subject["node_id"]) is None


class TestDirectModeForigiLiteral:
    """Tests for direct-mode forigi handling literal triples."""

    def test_forigi_literal_triple_direct(self, runner: CliRunner):
        """Direct-mode forigi should work for string literal triples."""
        subj_uuid = "z1000000-0000-0000-0000-000000000001"

        # Setup
        result = runner.invoke(app, [
            "nodo", "aldoni", subj_uuid, "-e", "eo::LitSubj", "--jes",
        ])
        assert result.exit_code == 0

        result = runner.invoke(app, [
            "predikato", "aldoni", "rdfs:label", "-e", "eo::etikedo", "--jes",
        ])
        assert result.exit_code == 0

        # Create a string literal triple
        result = runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:label", "test-value",
            "--str", "-l", "eo", "--jes",
        ])
        assert result.exit_code == 0, f"aldoni failed: {result.stdout}"

        # Delete the literal triple in direct mode
        result = runner.invoke(app, [
            "forigi", subj_uuid, "rdfs:label", "test-value", "--jes",
        ])
        assert result.exit_code == 0, f"forigi literal failed: {result.stdout}"
        assert "forigita" in result.stdout or "Arc deleted" in result.stdout

    def test_forigi_literal_triple_not_found(self, runner: CliRunner):
        """Direct-mode forigi should show 'not found' for non-matching literal."""
        subj_uuid = "z2000000-0000-0000-0000-000000000002"

        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::LitSubj2", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:label", "-e", "eo::etikedo", "--jes"])

        # Try to delete a non-existent literal triple
        result = runner.invoke(app, [
            "forigi", subj_uuid, "rdfs:label", "nonexistent-value", "--jes",
        ])
        assert result.exit_code == 1
        assert "ne trovita" in result.stdout or "not found" in result.stdout


class TestModifiDeprecatedConflict:
    """Tests for modifi with conflicting deprecated options."""

    def test_modifi_both_new_and_old_subject_fails(self, runner: CliRunner):
        """Using both --nova-subjekto and --new-subject should error."""
        subj_uuid = "z3000000-0000-0000-0000-000000000003"
        obj_uuid = "z4000000-0000-0000-0000-000000000004"
        new_subj_uuid = "z5000000-0000-0000-0000-000000000005"

        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::OldSubj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::OldObj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", new_subj_uuid, "-e", "eo::NewSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

        # Add triple
        result = runner.invoke(app, [
            "aldoni", subj_uuid, "rdf:type", obj_uuid, "--jes",
        ])
        assert result.exit_code == 0

        # Try modifi with both --nova-subjekto AND --new-subject
        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdf:type", obj_uuid,
            "--nova-subjekto", new_subj_uuid,
            "--new-subject", new_subj_uuid,
            "--jes",
        ])
        assert result.exit_code == 1
        assert "Ne eblas" in result.stdout or "Cannot use" in result.stdout

    def test_modifi_both_new_and_old_predicate_fails(self, runner: CliRunner):
        """Using both --nova-predikato and --new-predicate should error."""
        subj_uuid = "z6000000-0000-0000-0000-000000000006"
        obj_uuid = "z7000000-0000-0000-0000-000000000007"

        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::SubjPred", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::ObjPred", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:label", "-e", "eo::etikedo", "--jes"])

        result = runner.invoke(app, [
            "aldoni", subj_uuid, "rdf:type", obj_uuid, "--jes",
        ])
        assert result.exit_code == 0

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdf:type", obj_uuid,
            "--nova-predikato", "rdfs:label",
            "--new-predicate", "rdfs:label",
            "--jes",
        ])
        assert result.exit_code == 1
        assert "Ne eblas" in result.stdout or "Cannot use" in result.stdout

    def test_modifi_both_new_and_old_object_fails(self, runner: CliRunner):
        """Using both --nova-objekto and --new-object should error."""
        subj_uuid = "z8000000-0000-0000-0000-000000000008"
        obj_uuid = "z9000000-0000-0000-0000-000000000009"
        new_obj_uuid = "za0000000-0000-0000-0000-00000000000a"

        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::SubjObj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::ObjObj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", new_obj_uuid, "-e", "eo::NewObjObj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

        result = runner.invoke(app, [
            "aldoni", subj_uuid, "rdf:type", obj_uuid, "--jes",
        ])
        assert result.exit_code == 0

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdf:type", obj_uuid,
            "--nova-objekto", new_obj_uuid,
            "--new-object", new_obj_uuid,
            "--jes",
        ])
        assert result.exit_code == 1
        assert "Ne eblas" in result.stdout or "Cannot use" in result.stdout


class TestPredicateFTS:
    """Tests for predicate FTS5 search."""

    def test_predicate_search_by_label_via_fts(self, pred_svc):
        """Searching predicates by label should use FTS5."""
        # rdf:type is seeded with etikedoj={"eo":"tipo"}
        results = pred_svc.search("tipo")
        assert len(results) >= 1
        ids = [r["predicate_id"] for r in results]
        assert "rdf:type" in ids

    def test_predicate_search_by_partial_id(self, pred_svc):
        """Searching predicates by partial ID should fall back to LIKE."""
        pred_svc.create({"predicate_id": "custom:test123", "etikedoj": {"eo": "testo"}})
        results = pred_svc.search("custom:test")
        assert len(results) >= 1
        assert results[0]["predicate_id"] == "custom:test123"

    def test_predicate_fts_rebuilds_after_create(self, pred_svc):
        """Newly created predicates should be immediately searchable via FTS."""
        pred_svc.create({"predicate_id": "wdt:P9999", "etikedoj": {"eo": "unia propra"}})
        results = pred_svc.search("unia")
        assert len(results) >= 1
        assert results[0]["predicate_id"] == "wdt:P9999"

    def test_predicate_fts_search_empty(self, pred_svc):
        """Empty search should return all predicates."""
        # Make a new one to ensure we have data
        pred_svc.create({"predicate_id": "fts:empty-test"})
        results = pred_svc.search("")
        assert len(results) >= 1

    def test_predicate_search_with_special_chars(self, pred_svc):
        """FTS5 should handle special characters gracefully."""
        pred_svc.create({"predicate_id": "special:test", "etikedoj": {"eo": "hejt&cool"}})
        results = pred_svc.search("hejt")
        assert len(results) >= 1
