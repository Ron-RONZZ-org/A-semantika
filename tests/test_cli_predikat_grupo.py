"""Predikat-grupo CLI tests: aldoni, ls, vidi, modifi, forigi."""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


def test_predikat_grupo_aldoni_ls_vidi(runner: CliRunner) -> None:
    """Creating and viewing a group should work."""
    result = runner.invoke(app, ["predikat-grupo", "aldoni", "biologio", "-y"])
    assert result.exit_code == 0
    assert "kreita" in result.stdout

    result = runner.invoke(app, ["predikat-grupo", "ls"])
    assert result.exit_code == 0
    assert "biologio" in result.stdout

    result = runner.invoke(app, ["predikat-grupo", "vidi", "biologio"])
    assert result.exit_code == 0
    assert "biologio" in result.stdout


def test_predikat_grupo_modifi_rename(runner: CliRunner) -> None:
    """Renaming a group should work."""
    runner.invoke(app, ["predikat-grupo", "aldoni", "old", "-y"])
    result = runner.invoke(app, ["predikat-grupo", "modifi", "old", "new", "-y"])
    assert result.exit_code == 0
    assert "renomita" in result.stdout or "Renomita" in result.stdout or "new" in result.stdout


def test_predikat_grupo_importi_not_available(runner: CliRunner) -> None:
    """importi should show 'not available in P1'."""
    result = runner.invoke(app, ["predikat-grupo", "importi", "somefile.owl"])
    assert result.exit_code == 0
    assert "ne disponebla" in result.stdout or "not available" in result.stdout


def test_predikat_grupo_forigi(runner: CliRunner) -> None:
    """Deleting a group should work."""
    runner.invoke(app, ["predikat-grupo", "aldoni", "forigota", "-y"])
    result = runner.invoke(app, ["predikat-grupo", "forigi", "forigota", "-y"])
    assert result.exit_code == 0
    assert "Forigis" in result.stdout


def test_predikat_grupo_forigi_multiple(runner: CliRunner) -> None:
    """Deleting multiple groups at once should work."""
    runner.invoke(app, ["predikat-grupo", "aldoni", "group_a", "-y"])
    runner.invoke(app, ["predikat-grupo", "aldoni", "group_b", "-y"])
    result = runner.invoke(app, ["predikat-grupo", "forigi", "group_a", "group_b", "-y"])
    assert result.exit_code == 0
    assert "Forigis 2 el 2" in result.stdout


def test_predikat_grupo_forigi_single_no_confirm(runner: CliRunner) -> None:
    """Single group forigi without -y skips confirmation."""
    runner.invoke(app, ["predikat-grupo", "aldoni", "no-conf-group", "--jes"])
    result = runner.invoke(app, ["predikat-grupo", "forigi", "no-conf-group"])
    assert result.exit_code == 0
    assert "Forigis" in result.stdout or "forigita" in result.stdout
