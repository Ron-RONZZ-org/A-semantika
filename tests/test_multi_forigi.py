"""Multi-identifier forigi edge cases (Issue #13).

Extracted from test_edge_cases.py — TestNodoForigiMulti + TestPredikatoForigiMulti + TestPredikatGrupoForigiMulti.
"""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


class TestNodoForigiMulti:
    """Edge cases for multi-UUID nodo forigi."""

    def test_partial_failure_some_not_found(self, runner: CliRunner):
        """Some UUIDs not found should report errors but delete the rest."""
        runner.invoke(app, ["nodo", "aldoni", "a0000000-0000-0000-0000-000000000001", "-e", "eo::Exists1", "-y"])
        runner.invoke(app, ["nodo", "aldoni", "a0000000-0000-0000-0000-000000000002", "-e", "eo::Exists2", "-y"])
        result = runner.invoke(app, [
            "nodo", "forigi",
            "a0000000-0000-0000-0000-000000000001",
            "nonexistent-uuid",
            "a0000000-0000-0000-0000-000000000002",
            "-y",
        ])
        assert result.exit_code == 0
        assert "ne trovita" in result.stdout or "not found" in result.stdout
        assert "Forigis 2 el" in result.stdout or "Deleted 2 of" in result.stdout

    def test_all_not_found(self, runner: CliRunner):
        """All UUIDs not found should error."""
        result = runner.invoke(app, [
            "nodo", "forigi", "zzz-nonexistent-1", "zzz-nonexistent-2", "-y",
        ])
        assert result.exit_code == 1
        assert "Nenio forigebla" in result.stdout or "Nothing to delete" in result.stdout

    def test_no_args_shows_error(self, runner: CliRunner):
        """No args should show error about missing argument."""
        result = runner.invoke(app, ["nodo", "forigi"])
        assert result.exit_code in (1, 2)
        # Missing required argument should produce an error
        assert result.exit_code != 0


class TestPredikatoForigiMulti:
    """Edge cases for multi-predicate-id predikato forigi."""

    def test_partial_failure_some_not_found(self, runner: CliRunner):
        """Some predicate IDs not found should report errors but delete the rest."""
        runner.invoke(app, ["predikato", "aldoni", "wdt:P111", "-e", "eo::test111", "-y"])
        runner.invoke(app, ["predikato", "aldoni", "wdt:P112", "-e", "eo::test112", "-y"])
        result = runner.invoke(app, [
            "predikato", "forigi", "wdt:P111", "wdt:NOTEXIST", "wdt:P112", "-y",
        ])
        assert result.exit_code == 0
        assert "ne trovita" in result.stdout or "not found" in result.stdout
        assert "Forigis 2 el" in result.stdout or "Deleted 2 of" in result.stdout

    def test_all_not_found(self, runner: CliRunner):
        """All predicate IDs not found should error."""
        result = runner.invoke(app, [
            "predikato", "forigi", "wdt:NEVER1", "wdt:NEVER2", "-y",
        ])
        assert result.exit_code == 1
        assert "Nenio forigebla" in result.stdout or "Nothing to delete" in result.stdout


class TestPredikatGrupoForigiMulti:
    """Edge cases for multi-group-name predikat-grupo forigi."""

    def test_partial_failure_some_not_found(self, runner: CliRunner):
        """Some group names not found should report errors but delete the rest."""
        runner.invoke(app, ["predikat-grupo", "aldoni", "grp_exists", "-y"])
        result = runner.invoke(app, [
            "predikat-grupo", "forigi", "grp_exists", "grp_nonexistent", "-y",
        ])
        assert result.exit_code == 0
        assert "ne trovita" in result.stdout or "not found" in result.stdout
        assert "Forigis 1 el" in result.stdout or "Deleted 1 of" in result.stdout

    def test_all_not_found(self, runner: CliRunner):
        """All group names not found should error."""
        result = runner.invoke(app, [
            "predikat-grupo", "forigi", "no_such_group_1", "no_such_group_2", "-y",
        ])
        assert result.exit_code == 1
        assert "Nenio forigebla" in result.stdout or "Nothing to delete" in result.stdout
