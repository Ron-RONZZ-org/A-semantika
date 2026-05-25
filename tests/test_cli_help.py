"""Help and basic command structure tests."""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


def test_help_shows_commands(runner: CliRunner) -> None:
    """Calling without args should show help with all commands."""
    result = runner.invoke(app, [])
    # Click 8.x exits with code 2 for no_args_is_help (UsageError)
    assert result.exit_code in (0, 2), f"Unexpected exit code: {result.exit_code}"
    assert "aldoni" in result.stdout
    assert "modifi" in result.stdout
    assert "forigi" in result.stdout
    assert "serci" in result.stdout
    assert "vidi" in result.stdout
    assert "eksporti" in result.stdout
    assert "nodo" in result.stdout
    assert "predikato" in result.stdout
    assert "predikat-grupo" in result.stdout


def test_nodo_help(runner: CliRunner) -> None:
    """Nodo subcommand should show its subcommands."""
    result = runner.invoke(app, ["nodo", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.stdout
    assert "aldoni" in result.stdout


def test_predikato_help(runner: CliRunner) -> None:
    """Predikato subcommand should show its subcommands."""
    result = runner.invoke(app, ["predikato", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.stdout
    assert "aldoni" in result.stdout


def test_predikat_grupo_help(runner: CliRunner) -> None:
    """Predikat-grupo subcommand should show its subcommands."""
    result = runner.invoke(app, ["predikat-grupo", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.stdout


def test_help_shows_jes_not_yes(runner: CliRunner) -> None:
    """Help text should mention --jes as the canonical flag."""
    result = runner.invoke(app, ["nodo", "aldoni", "--help"])
    assert result.exit_code == 0
    assert "--jes" in result.stdout
    # --yes may appear as alias in help, but --jes must be shown
