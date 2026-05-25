"""Special characters and empty/trivial input edge cases.

Extracted from test_edge_cases.py — TestSpecialCharsInData + TestEmptyInputs.
"""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


class TestSpecialCharsInData:
    """Edge cases with special characters."""

    def test_node_with_special_chars_label(self, runner: CliRunner):
        """Node with special chars in labels should work."""
        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", "eo::Testo kun ŝanĝoĵ!@#$%",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "kreita" in result.stdout or "Created" in result.stdout

    def test_triple_with_special_chars_literal(self, runner: CliRunner):
        """Triple with special chars in literal value should work."""
        subj_uuid = "f4000000-0000-0000-0000-000000000004"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::SpecSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:label", "-e", "eo::etikedo", "--jes"])

        result = runner.invoke(app, [
            "aldoni", subj_uuid[:8], "rdfs:label",
            'Testo with "quotes" & <html>',
            "--str", "--jes",
        ])
        assert result.exit_code == 0

    def test_long_label_value(self, runner: CliRunner):
        """Very long label values should not crash."""
        long_label = "A" * 500
        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", f"eo::{long_label}",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "kreita" in result.stdout or "Created" in result.stdout

    def test_very_long_literal(self, runner: CliRunner):
        """Very long literal values should not crash."""
        subj_uuid = "f5000000-0000-0000-0000-000000000005"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::LongSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        long_value = "X" * 2000
        result = runner.invoke(app, [
            "aldoni", subj_uuid[:8], "rdfs:comment", long_value,
            "--str", "--jes",
        ])
        assert result.exit_code == 0


class TestEmptyInputs:
    """Empty or trivial inputs should not crash."""

    def test_nodo_serci_empty_string(self, runner: CliRunner):
        """Searching with empty string should not crash."""
        result = runner.invoke(app, ["nodo", "serci", ""])
        assert result.exit_code in (0, 2)

    def test_predikato_serci_empty(self, runner: CliRunner):
        """Predicate search with empty string should not crash."""
        result = runner.invoke(app, ["predikato", "serci", ""])
        assert result.exit_code in (0, 2)
