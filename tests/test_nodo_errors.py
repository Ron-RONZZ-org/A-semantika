"""Nodo aldoni error handling and ambiguous prefix edge cases.

Extracted from test_edge_cases.py — TestNodoAldoniErrorHandling + TestNodoForigiAmbiguousPrefix.
"""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


class TestNodoAldoniErrorHandling:
    """Graceful error handling for nodo aldoni (issue #15)."""

    def test_nodo_aldoni_custom_id_works(self, runner: CliRunner):
        """Human-readable ID as positional arg should work (C1 removed)."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "SPACO", "-e", "eo::Spaco", "-y",
        ])
        assert result.exit_code == 0
        assert "kreita" in result.stdout or "Created" in result.stdout

    def test_nodo_aldoni_duplicate_id_friendly(self, runner: CliRunner, node_svc):
        """Using an existing node_id should show friendly error (C2+C3)."""
        existing_id = "DUPLICATO"
        node_svc.create({"node_id": existing_id, "etikedoj": {"eo": "Ekzistanta"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", existing_id, "-y",
        ])
        assert result.exit_code == 1
        # Must show a meaningful error, not a traceback
        assert "already exists" in result.stdout
        assert "modifi" in result.stdout
        assert "Traceback" not in result.stdout

    def test_nodo_aldoni_auto_id_no_collision(self, runner: CliRunner, node_svc):
        """Auto-generated node_id (no positional arg) should still work."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "-e", "eo::Aŭtomata", "-y",
        ])
        assert result.exit_code == 0
        assert "Nodo kreita" in result.stdout or "Node created" in result.stdout

    def test_nodo_forigi_twice_is_safe(self, runner: CliRunner, node_svc):
        """Deleting an already-deleted node should not crash."""
        node = node_svc.create({"etikedoj": {"eo": "Forigota"}})
        # First delete
        result1 = runner.invoke(app, [
            "nodo", "forigi", node["node_id"][:8], "-y",
        ])
        assert result1.exit_code == 0
        # Second delete — should not crash
        result2 = runner.invoke(app, [
            "nodo", "forigi", node["node_id"][:8], "-y",
        ])
        assert result2.exit_code == 1
        assert "ne trovita" in result2.stdout or "not found" in result2.stdout
        assert "Traceback" not in result2.stdout


class TestNodoForigiAmbiguousPrefix:
    """Ambiguous node_id prefix in multi-forigi should report per-item."""

    def test_ambiguous_prefix_reported(self, runner: CliRunner, node_svc):
        """Ambiguous prefix should report error and not block other deletions."""
        node_svc.create({"node_id": "bbbbbbbb-0000-0000-0000-000000000001", "etikedoj": {"eo": "AmbA"}})
        node_svc.create({"node_id": "bbbbbbba-0000-0000-0000-000000000001", "etikedoj": {"eo": "AmbB"}})
        node_svc.create({"node_id": "cccccccc-0000-0000-0000-000000000001", "etikedoj": {"eo": "Clear"}})

        # "bbbb" matches both AmbA and AmbB → ambiguous
        result = runner.invoke(app, [
            "nodo", "forigi", "bbbb", "cccccccc", "-y",
        ])
        assert result.exit_code == 0
        assert "ambigua" in result.stdout or "ambiguous" in result.stdout
        assert "Forigis 1 el" in result.stdout or "Deleted 1 of" in result.stdout
