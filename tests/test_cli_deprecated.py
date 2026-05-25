"""Deprecated alias backward-compat tests (Issue #10)."""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


def test_serci_subject_deprecated_alias(runner: CliRunner) -> None:
    """Old --subject flag should still work (deprecated)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepSubj", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    uuid_prefix = None
    for line in ls_result.stdout.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2 and "DepSubj" in " ".join(parts[1:]):
            uuid_prefix = parts[0]
            break
    if uuid_prefix:
        result = runner.invoke(app, ["serci", "--subject", uuid_prefix])
        assert result.exit_code == 0


def test_serci_predicate_deprecated_alias(runner: CliRunner) -> None:
    """Old --predicate flag should still work (deprecated)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepPredSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepPredObj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]
    if len(uuids) >= 2:
        runner.invoke(app, ["aldoni", uuids[0], "rdf:type", uuids[1], "--jes"])
        result = runner.invoke(app, ["serci", "--predicate", "rdf:type"])
        assert result.exit_code == 0


def test_serci_object_deprecated_alias(runner: CliRunner) -> None:
    """Old --object flag should still work (deprecated)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepObjSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::DepObjObj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]
    if len(uuids) >= 2:
        runner.invoke(app, ["aldoni", uuids[0], "rdf:type", uuids[1], "--jes"])
        result = runner.invoke(app, ["serci", "--object", uuids[1]])
        assert result.exit_code == 0
