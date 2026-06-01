"""Nodo aldoni error handling and ambiguous prefix edge cases.

Extracted from test_edge_cases.py — TestNodoAldoniErrorHandling + TestNodoForigiAmbiguousPrefix.
"""
from __future__ import annotations

import json

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

    def test_nodo_aldoni_duplicate_id_noop(self, runner: CliRunner, node_svc):
        """Using an existing node_id with same data should show 'no change'."""
        existing_id = "DUPLICATO"
        node_svc.create({"node_id": existing_id, "etikedoj": {"eo": "Ekzistanta"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", existing_id, "-y",
        ])
        assert result.exit_code == 0
        # No changes → should show "no change" message, not a traceback
        assert "neniu ŝanĝo" in result.stdout.lower() or "no change" in result.stdout.lower()
        assert "Traceback" not in result.stdout

    def test_nodo_aldoni_duplicate_id_with_changes_shows_preview(self, runner: CliRunner, node_svc):
        """Using an existing node_id with different labels shows preview before error."""
        existing_id = "DUPLICATO2"
        node_svc.create({"node_id": existing_id, "etikedoj": {"eo": "OldLabel"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", existing_id, "-e", "eo::NewLabel",
        ])
        # Interactive: no stdin → confirm_action returns False → falls through to raw error
        assert result.exit_code == 1
        # Should show preview with old and new values (shown before confirm prompt)
        assert "OldLabel" in result.stdout
        assert "NewLabel" in result.stdout
        # Should show the "already exists" / "jam ekzistas" info message
        assert "jam ekzistas" in result.stdout.lower() or "already exists" in result.stdout.lower()
        # The raw DB error (UNIQUE constraint) should NOT appear
        assert "UNIQUE constraint" not in result.stdout

    def test_nodo_aldoni_duplicate_id_with_changes_silent_yes(self, runner: CliRunner, node_svc):
        """Using -y with different labels silently updates."""
        existing_id = "DUPLICATO3"
        node_svc.create({"node_id": existing_id, "etikedoj": {"eo": "OldLabel"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", existing_id, "-e", "eo::NewLabel", "-y",
        ])
        assert result.exit_code == 0
        # -y mode updates silently (no extra output), just exit 0
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
        """Ambiguous prefix should report error with match count and not block other deletions."""
        node_svc.create({"node_id": "bbbbbbbb-0000-0000-0000-000000000001", "etikedoj": {"eo": "AmbA"}})
        node_svc.create({"node_id": "bbbbbbba-0000-0000-0000-000000000001", "etikedoj": {"eo": "AmbB"}})
        node_svc.create({"node_id": "cccccccc-0000-0000-0000-000000000001", "etikedoj": {"eo": "Clear"}})

        # "bbbb" matches both AmbA and AmbB → ambiguous
        result = runner.invoke(app, [
            "nodo", "forigi", "bbbb", "cccccccc", "-y",
        ])
        assert result.exit_code == 0
        assert "ambigua" in result.stdout or "ambiguous" in result.stdout
        # Must show match count in error (fix for dropped exception detail)
        assert "2" in result.stdout
        assert "matches" in result.stdout
        assert "Forigis 1 el" in result.stdout or "Deleted 1 of" in result.stdout

    def test_ambiguous_prefix_mixed_errors(self, runner: CliRunner, node_svc):
        """Mixed ambiguous + not-found + valid IDs should report all error types."""
        node_svc.create({"node_id": "dddddddd-0000-0000-0000-000000000001", "etikedoj": {"eo": "AmbC"}})
        node_svc.create({"node_id": "dddddddc-0000-0000-0000-000000000001", "etikedoj": {"eo": "AmbD"}})
        node_svc.create({"node_id": "eeeeeeee-0000-0000-0000-000000000001", "etikedoj": {"eo": "Valid"}})

        result = runner.invoke(app, [
            "nodo", "forigi", "dddd", "zzzz-nonexistent", "eeeeeeee", "-y",
        ])
        assert result.exit_code == 0
        assert "ambigua" in result.stdout or "ambiguous" in result.stdout
        assert "ne trovita" in result.stdout or "not found" in result.stdout
        assert "2" in result.stdout
        assert "matches" in result.stdout
        assert "Forigis 1 el" in result.stdout or "Deleted 1 of" in result.stdout


class TestNodoAldoniLangIndependentLabel:
    """Language-independent labels (no LANG:: prefix) in nodo aldoni."""

    def test_aldoni_lang_independent_label(self, runner: CliRunner, node_svc):
        """Plain text without :: separator stores as language-independent label."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "CITY", "-e", "Paris", "-y",
        ])
        assert result.exit_code == 0
        assert "kreita" in result.stdout.lower() or "created" in result.stdout.lower()
        node = node_svc.get("CITY")
        assert node is not None
        labels = json.loads(node.get("etikedoj", "{}"))
        # Should be stored with empty-string key (language-independent)
        assert "" in labels
        assert labels[""] == "Paris"

    def test_aldoni_mixed_labels(self, runner: CliRunner, node_svc):
        """Mix of lang-specific and language-independent labels."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "MIXED", "-e", "Paris", "-e", "en::Paris", "-y",
        ])
        assert result.exit_code == 0
        node = node_svc.get("MIXED")
        assert node is not None
        labels = json.loads(node.get("etikedoj", "{}"))
        assert labels.get("") == "Paris"
        assert labels.get("en") == "Paris"

    def test_aldoni_lang_independent_difino(self, runner: CliRunner, node_svc):
        """Plain text for -d stores as language-independent definition."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "RIVER", "-d", "A large natural stream of water", "-y",
        ])
        assert result.exit_code == 0
        node = node_svc.get("RIVER")
        assert node is not None
        defns = json.loads(node.get("difinoj", "{}"))
        assert "" in defns
        assert "stream" in defns[""]

    def test_modifi_add_lang_independent_label(self, runner: CliRunner, node_svc):
        """modifi -e with plain text adds language-independent label."""
        node_svc.create({"node_id": "TEST", "etikedoj": {"eo": "Testo"}})
        result = runner.invoke(app, [
            "nodo", "modifi", "TEST", "-e", "GlobalName", "-y",
        ])
        assert result.exit_code == 0
        node = node_svc.get("TEST")
        assert node is not None
        labels = json.loads(node.get("etikedoj", "{}"))
        assert "" in labels
        assert labels[""] == "GlobalName"
        # Should also keep the existing eo label
        assert labels.get("eo") == "Testo"


class TestNodoAldoniPreviewOnDuplicate:
    """Modification preview shown when duplicate node_id is provided."""

    def test_preview_shown_on_duplicate(self, runner: CliRunner, node_svc):
        """Different labels trigger preview on duplicate node_id."""
        node_svc.create({"node_id": "PREVIEW", "etikedoj": {"eo": "Old", "en": "OldEn"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", "PREVIEW", "-e", "eo::New",
        ])
        # Not confirmed (no stdin) → exit 1
        assert result.exit_code == 1
        # Preview table should show old vs new labels
        assert "Old" in result.stdout
        assert "New" in result.stdout
        # Old label that wasn't touched should also appear
        assert "OldEn" in result.stdout

    def test_noop_duplicate_no_preview(self, runner: CliRunner, node_svc):
        """Same labels on duplicate node_id shows 'no change', no preview."""
        node_svc.create({"node_id": "NOOP", "etikedoj": {"eo": "Same"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", "NOOP", "-e", "eo::Same", "-y",
        ])
        assert result.exit_code == 0
        assert "neniu ŝanĝo" in result.stdout.lower() or "no change" in result.stdout.lower()

    def test_lang_independent_label_on_duplicate(self, runner: CliRunner, node_svc):
        """Language-independent label in preview on duplicate."""
        node_svc.create({"node_id": "GLOBAL", "etikedoj": {"": "Paris"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", "GLOBAL", "-e", "London",
        ])
        assert result.exit_code == 1
        assert "Paris" in result.stdout
        assert "London" in result.stdout

    def test_duplicate_decline_shows_nuligita(self, runner: CliRunner, node_svc):
        """Declining duplicate update should show 'nuligita', not raw error."""
        node_svc.create({"node_id": "DUPLO", "etikedoj": {"eo": "OldLabel"}})
        # Provide "n" (no) as input → confirm_action returns False → should show "nuligita"
        result = runner.invoke(app, [
            "nodo", "aldoni", "DUPLO", "-e", "eo::NewLabel",
        ], input="n\n")
        # Should show "Canceled" (exit 0), not the raw "already exists" error
        assert result.exit_code == 0, f"Got exit {result.exit_code}: {result.stdout}"
        assert "nuligita" in result.stdout.lower() or "canceled" in result.stdout.lower() or "annulé" in result.stdout.lower()


class TestNodoAldoniSimilarNodeUpdate:
    """Similar node detection should offer inline update."""

    def test_similar_node_decline_shows_nuligita(self, runner: CliRunner, node_svc):
        """Declining similar node update should show 'nuligita'."""
        # Existing node with full name. New node uses a SUBSET of words
        # (word-subset check in similar detection).
        node_svc.create({"node_id": "EXISTO", "etikedoj": {"eo": "Ekzistanta Nodo Granda"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", "NOVA", "-e", "eo::Ekzistanta Nodo",
        ], input="n\n")
        assert result.exit_code == 0, f"Got exit {result.exit_code}: {result.stdout}"
        assert "nuligita" in result.stdout.lower() or "canceled" in result.stdout.lower() or "annulé" in result.stdout.lower()
        # The existing node should still exist
        assert node_svc.get("EXISTO") is not None

    def test_similar_node_update_with_yes(self, runner: CliRunner, node_svc):
        """Similar node with -y flag should silently update existing."""
        # Existing has "Ekzistanta Nodo Granda" → new "Ekzistanta Nodo" is subset words
        node_svc.create({"node_id": "EXISTO2", "etikedoj": {"eo": "Ekzistanta Nodo Granda"}})
        result = runner.invoke(app, [
            "nodo", "aldoni", "NOVA2", "-e", "eo::Ekzistanta Nodo", "-y",
        ])
        assert result.exit_code == 0, f"Got exit {result.exit_code}: {result.stdout}"
        # Existing node should have been updated with the new label
        existing = node_svc.get("EXISTO2")
        assert existing is not None
        import json
        labels = json.loads(existing["etikedoj"])
        assert labels.get("eo") == "Ekzistanta Nodo"
        # New node should NOT exist (deleted after similar detection)
        assert node_svc.get("NOVA2") is None
