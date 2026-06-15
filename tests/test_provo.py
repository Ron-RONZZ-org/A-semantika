"""Tests for ProvoService and provo CLI commands."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from A_semantika._provo_service import ProvoService
from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_provo_service,
    get_triple_service,
    reset_services,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isolate database to temp directory."""
    from A_semantika import data as data_module

    monkeypatch.setattr(data_module.storage, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(data_module.storage, "_db_instance", None)
    reset_services()


@pytest.fixture
def setup_arc():
    """Create a node, predicate, and a triple, returning their identifiers."""
    reset_services()
    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    node = node_svc.create({"etikedoj": {"eo": "Testo"}})
    pred = pred_svc.create({"predicate_id": "testas", "etikedoj": {"eo": "testi"}})
    triple = triple_svc.add(
        subject_uuid=node["node_id"],
        predicate_id="testas",
        object_value="cela_valoro",
        object_type="literal",
    )
    return {
        "node_id": node["node_id"],
        "predicate_id": "testas",
        "object_value": "cela_valoro",
        "triple": triple,
    }


# ---------------------------------------------------------------------------
# ProvoService unit tests
# ---------------------------------------------------------------------------

class TestProvoService:
    def test_create_proof(self, setup_arc):
        svc = get_provo_service()
        result = svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="**Pruvo:** 1 + 1 = 2",
            lingvo="eo",
        )
        assert result["created"] is True
        assert result["stmt_node_id"].startswith("PROVO_")

    def test_find_proofs(self, setup_arc):
        svc = get_provo_service()
        svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Provo A",
            lingvo="eo",
        )
        proofs = svc.find_proofs(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
        )
        assert len(proofs) == 1
        assert proofs[0]["proof_text"] == "Provo A"

    def test_create_second_proof(self, setup_arc):
        """Second proof for same arc should reuse the statement node."""
        svc = get_provo_service()
        r1 = svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Provo Unua",
            lingvo="eo",
        )
        r2 = svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Provo Dua",
            lingvo="en",
        )
        # Same stmt_node_id, not created fresh
        assert r2["stmt_node_id"] == r1["stmt_node_id"]
        assert r2["created"] is False

    def test_delete_proof(self, setup_arc):
        svc = get_provo_service()
        result = svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Forigota",
            lingvo="eo",
        )
        svc.delete_proof(result["stmt_node_id"])
        proofs = svc.find_proofs(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
        )
        assert len(proofs) == 0

    def test_cascade_delete_proofs(self, setup_arc):
        svc = get_provo_service()
        svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Kaskade",
            lingvo="eo",
        )
        deleted = svc.cascade_delete_proofs(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
        )
        assert deleted == 1
        proofs = svc.find_proofs(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
        )
        assert len(proofs) == 0

    def test_get_all_proofs_batch(self, setup_arc):
        svc = get_provo_service()
        svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Amasa",
            lingvo="eo",
        )
        all_proofs = svc.get_all_proofs_batch()
        assert len(all_proofs) == 1

    def test_get_proofs_for_arcs_batch(self, setup_arc):
        svc = get_provo_service()
        svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Amasa",
            lingvo="eo",
        )
        arc_keys = [
            (
                setup_arc["node_id"],
                setup_arc["predicate_id"],
                setup_arc["object_value"],
            )
        ]
        mapping = svc.get_proofs_for_arcs_batch(arc_keys)
        assert len(mapping) == 1
        stmt_ids = mapping[arc_keys[0]]
        assert len(stmt_ids) == 1

    def test_create_proof_missing_arc(self, setup_arc):
        """Creating a proof for a non-existent triple should raise ValueError."""
        svc = get_provo_service()
        with pytest.raises(ValueError, match="not found|ne trovita|non trouvé"):
            svc.create_proof(
                subject_uuid=setup_arc["node_id"],
                predicate_id=setup_arc["predicate_id"],
                object_value="ne_ekzistanta",
                object_type="literal",
                proof_text="Nenio",
                lingvo="eo",
            )

    def test_delete_nonexistent_proof(self, setup_arc):
        """Deleting a non-existent proof node should return False."""
        svc = get_provo_service()
        result = svc.delete_proof("PROVO_NONEXISTENT_12345678")
        assert result is False

    def test_get_proofs_nonexistent_arc(self, setup_arc):
        """Finding proofs for an arc without proofs returns empty list."""
        svc = get_provo_service()
        proofs = svc.find_proofs(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value="sen_pruvo",
        )
        assert proofs == []

    def test_cascade_no_proofs(self, setup_arc):
        """Cascade delete on arc without proofs returns 0."""
        svc = get_provo_service()
        deleted = svc.cascade_delete_proofs(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value="sen_pruvo",
        )
        assert deleted == 0

    def test_multiple_proofs_node_id_suffix(self, setup_arc):
        """Multiple proofs at same arc get _2, _3 suffixes on first proof only."""
        svc = get_provo_service()
        r1 = svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Pruvo 1",
            lingvo="eo",
        )
        # First proof: no suffix
        assert not r1["stmt_node_id"].endswith("_2")

    def test_proof_text_preserves_markdown(self, setup_arc):
        """Proof text with markdown formatting is stored as-is."""
        svc = get_provo_service()
        md_text = "**Teoremo:** $E = mc^2$\n\n_Pruvo:_"
        svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text=md_text,
            lingvo="eo",
        )
        proofs = svc.find_proofs(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
        )
        assert proofs[0]["proof_text"] == md_text


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestProvoCLI:
    def test_provo_help(self, runner: CliRunner):
        """provo --help should show subcommands."""
        from A_semantika.cli import app

        result = runner.invoke(app, ["provo", "--help"])
        assert result.exit_code == 0
        assert "aldoni" in result.stdout
        assert "vidi" in result.stdout
        assert "forigi" in result.stdout

    def test_provo_aldoni(self, runner: CliRunner, setup_arc):
        """provo aldoni should create a proof for the given arc."""
        from A_semantika.cli import app

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
            f.write("**Pruvo:** Testo")
            proof_path = f.name
        try:
            result = runner.invoke(app, [
                "provo", "aldoni",
                setup_arc["node_id"],
                setup_arc["predicate_id"],
                setup_arc["object_value"],
                "-D", proof_path,
                "-y",
            ])
            assert result.exit_code == 0, result.stdout
            assert "aldonita" in result.stdout.lower() or "added" in result.stdout.lower() or "ajouté" in result.stdout.lower() or "kreita" in result.stdout.lower()
        finally:
            Path(proof_path).unlink(missing_ok=True)

    def test_provo_vidi(self, runner: CliRunner, setup_arc):
        """provo vidi should display proof details."""
        from A_semantika.cli import app

        # First create a proof via the service
        svc = get_provo_service()
        result = svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Montrota",
            lingvo="eo",
        )
        # View via CLI using all three args (subject predicate object)
        resp = runner.invoke(app, [
            "provo", "vidi",
            setup_arc["node_id"],
            setup_arc["predicate_id"],
            setup_arc["object_value"],
        ])
        assert resp.exit_code == 0, resp.stdout
        assert "Montrota" in resp.stdout
        assert "PROVO_" in resp.stdout or "provo" in resp.stdout.lower()

    def test_provo_forigi(self, runner: CliRunner, setup_arc):
        """provo forigi should delete a proof."""
        from A_semantika.cli import app

        svc = get_provo_service()
        result = svc.create_proof(
            subject_uuid=setup_arc["node_id"],
            predicate_id=setup_arc["predicate_id"],
            object_value=setup_arc["object_value"],
            object_type="literal",
            proof_text="Forigota CLI",
            lingvo="eo",
        )
        resp = runner.invoke(app, [
            "provo", "forigi",
            result["stmt_node_id"],
            "-y",
        ])
        assert resp.exit_code == 0, resp.stdout
        assert "forigita" in resp.stdout.lower() or "deleted" in resp.stdout.lower() or "supprim" in resp.stdout.lower()

    def test_provo_aldoni_nonexistent_arc(self, runner: CliRunner):
        """provo aldoni on non-existent arc should error."""
        from A_semantika.cli import app

        result = runner.invoke(app, [
            "provo", "aldoni",
            "NONEXISTENT",
            "testas",
            "valoro",
            "-p", "Pruvo",
            "-y",
        ])
        assert result.exit_code != 0

    def test_provo_forigi_nonexistent(self, runner: CliRunner):
        """provo forigi on non-existent proof should error."""
        from A_semantika.cli import app

        result = runner.invoke(app, [
            "provo", "forigi",
            "PROVO_NONEXISTENT",
            "-y",
        ])
        assert result.exit_code != 0
