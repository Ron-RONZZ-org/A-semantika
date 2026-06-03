"""B3: validate_type_flags exit path tests."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app


def test_aldoni_lingvo_without_str_exits_error(runner: CliRunner) -> None:
    """--lingvo without --str should exit with error (B3)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::B3Subj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    if not lines:
        pytest.skip("No nodes available")
    subj_id = lines[0].split()[0]

    # Try aldoni with --lingvo but no --str — should error, not just warn
    result = runner.invoke(app, [
        "aldoni", subj_id, "rdf:type", "Hundo", "--lingvo", "eo", "--jes",
    ])
    assert result.exit_code == 1
    assert "bezonas" in result.stdout or "requires" in result.stdout


def test_aldoni_unuo_without_int_or_float_exits_error(runner: CliRunner) -> None:
    """--unuo without --int or --float should exit with error (B3)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::B3UnuoSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    if not lines:
        pytest.skip("No nodes available")
    subj_id = lines[0].split()[0]

    # Try aldoni with --unuo but no --int or --float — should error
    result = runner.invoke(app, [
        "aldoni", subj_id, "rdf:type", "Hundo", "--unuo", "abc123", "--jes",
    ])
    assert result.exit_code == 1
    assert "bezonas" in result.stdout or "requires" in result.stdout


def test_aldoni_str_with_kodlingvo_creates_code_snippet(runner: CliRunner) -> None:
    """--str with --kodlingvo should create a code snippet (not plain string)."""
    runner.invoke(app, ["nodo", "aldoni", "B3KodSubj", "-e", "eo::B3KodSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    result = runner.invoke(app, [
        "aldoni", "B3KodSubj", "rdf:type", "--str", "print('hello')", "--kodlingvo", "python", "--jes",
    ])
    assert result.exit_code == 0, f"--str --kodlingvo failed: {result.stdout}"
    assert "kreita" in result.stdout or "created" in result.stdout or "Arc" in result.stdout


def test_aldoni_kodlingvo_without_kodbloko_and_without_str_exits_error(runner: CliRunner) -> None:
    """--kodlingvo without --kodbloko and without --str should exit with error."""
    runner.invoke(app, ["nodo", "aldoni", "B3KodSubj2", "-e", "eo::B3KodSubj2", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    # No --str, no --kodbloko — just a positional URI object with --kodlingvo
    result = runner.invoke(app, [
        "aldoni", "B3KodSubj2", "rdf:type", "Hundo", "--kodlingvo", "python", "--jes",
    ])
    assert result.exit_code == 1
    assert "bezonas" in result.stdout or "requires" in result.stdout
