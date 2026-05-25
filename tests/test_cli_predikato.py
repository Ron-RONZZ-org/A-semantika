"""Predikato CLI tests: aldoni, ls, vidi, serci, forigi."""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


def test_predikato_aldoni_and_ls(runner: CliRunner) -> None:
    """Creating a predicate and listing it should work."""
    result = runner.invoke(app, [
        "predikato", "aldoni", "wdt:P31",
        "-e", "eo::estas tipo de",
        "-y",
    ])
    assert result.exit_code == 0
    assert "kreita" in result.stdout

    result = runner.invoke(app, ["predikato", "ls"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout


def test_predikato_vidi(runner: CliRunner) -> None:
    """Viewing a predicate should show details."""
    runner.invoke(app, ["predikato", "aldoni", "wdt:P31", "-e", "eo::tipo", "-y"])
    result = runner.invoke(app, ["predikato", "vidi", "wdt:P31"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout


def test_predikato_search(runner: CliRunner) -> None:
    """Searching predicates should work."""
    runner.invoke(app, ["predikato", "aldoni", "wdt:P31", "-e", "eo::tipo", "-y"])
    result = runner.invoke(app, ["predikato", "serci", "tipo"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout or "tipo" in result.stdout


def test_predikato_forigi_multiple(runner: CliRunner) -> None:
    """Deleting multiple predicates at once should work."""
    runner.invoke(app, ["predikato", "aldoni", "wdt:P99", "-e", "eo::test99", "-y"])
    runner.invoke(app, ["predikato", "aldoni", "wdt:P100", "-e", "eo::test100", "-y"])
    result = runner.invoke(app, ["predikato", "forigi", "wdt:P99", "wdt:P100", "-y"])
    assert result.exit_code == 0
    assert "Forigis 2 el 2" in result.stdout


def test_predikato_forigi_single_no_confirm(runner: CliRunner) -> None:
    """Single predicate forigi without -y skips confirmation."""
    runner.invoke(app, ["predikato", "aldoni", "wdt:X14", "-e", "eo::NoConfPred", "--jes"])
    result = runner.invoke(app, ["predikato", "forigi", "wdt:X14"])
    assert result.exit_code == 0
    assert "Forigis" in result.stdout or "forigita" in result.stdout
