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


def test_predikato_forigi_with_triples_cascades(runner: CliRunner) -> None:
    """Bug 2: predicate forigi with referencing triples should cascade-delete them."""
    # Create predicate
    runner.invoke(app, ["predikato", "aldoni", "test:pubjaro", "-e", "eo::pubjaro", "-y"])
    # Create a node + triple using the predicate
    runner.invoke(app, ["nodo", "aldoni", "TEST_BOOK", "-e", "eo::libro", "-y"])
    runner.invoke(app, [
        "aldoni", "TEST_BOOK", "test:pubjaro", "2024",
        "--str", "-l", "eo", "-y",
    ])
    # Verify triple exists via search
    r1 = runner.invoke(app, ["serci", "--subjekto", "TEST_BOOK", "--predikato", "test:pubjaro"])
    assert r1.exit_code == 0
    assert "2024" in r1.stdout
    # Delete predicate — should cascade
    result = runner.invoke(app, ["predikato", "forigi", "test:pubjaro", "-y"])
    assert result.exit_code == 0, f"Got exit {result.exit_code}: {result.stdout}"
    assert "Forigis" in result.stdout
    # Predicate should be gone
    r2 = runner.invoke(app, ["predikato", "vidi", "test:pubjaro"])
    assert r2.exit_code != 0
    # Triple should also be deleted (search returns nothing)
    r3 = runner.invoke(app, ["serci", "--subjekto", "TEST_BOOK", "--predikato", "test:pubjaro"])
    assert r3.exit_code == 0
    assert "2024" not in r3.stdout


def test_predikato_forigi_with_triples_shows_warning(runner: CliRunner) -> None:
    """Bug 2: predicate forigi with triples should show warning in preview."""
    runner.invoke(app, ["predikato", "aldoni", "test:pubyear", "-e", "eo::pubjaro", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "TB2", "-e", "eo::libro", "-y"])
    runner.invoke(app, ["aldoni", "TB2", "test:pubyear", "2024", "--str", "-y"])
    result = runner.invoke(app, ["predikato", "forigi", "test:pubyear"], input="n\n")
    assert result.exit_code == 0
    # Should mention triples will be deleted
    assert "triples" in result.stdout.lower() or "arkoj" in result.stdout.lower()
