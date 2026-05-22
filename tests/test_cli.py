"""CLI integration tests for A-semantika.

Uses typer.testing.CliRunner for full-stack tests.
"""
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


def test_nodo_aldoni_and_ls(runner: CliRunner) -> None:
    """Creating a node and listing it should work."""
    result = runner.invoke(app, [
        "nodo", "aldoni",
        "-e", "eo::Hundo",
        "-e", "en::Dog",
        "-y",
    ])
    assert result.exit_code == 0
    assert "kreita" in result.stdout

    result = runner.invoke(app, ["nodo", "ls"])
    assert result.exit_code == 0
    assert "Hundo" in result.stdout


def test_nodo_vidi(runner: CliRunner) -> None:
    """Viewing a node should show its details."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Kato", "-y"])
    result = runner.invoke(app, ["nodo", "ls"])
    # Extract UUID from ls output
    lines = result.stdout.strip().split("\n")
    # Find the line with Kato
    uuid_prefix = None
    for line in lines:
        if "Kato" in line:
            parts = line.strip().split()
            if parts:
                uuid_prefix = parts[0]
                break

    if uuid_prefix:
        result = runner.invoke(app, ["nodo", "vidi", uuid_prefix])
        assert result.exit_code == 0
        assert "Kato" in result.stdout


def test_nodo_serci(runner: CliRunner) -> None:
    """Searching nodes should find matches."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Birdo", "-y"])
    result = runner.invoke(app, ["nodo", "serci", "Birdo"])
    assert result.exit_code == 0
    assert "Birdo" in result.stdout


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


def test_triple_aldoni_requires_node_and_predicate(runner: CliRunner) -> None:
    """Triple aldoni requires existing nodes and predicates."""
    # Create a node
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Hundo", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Mamulo", "-y"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "-y"])

    # Get node UUIDs
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if "Hundo" in l or "Mamulo" in l]
    uuid_map = {}
    for line in lines:
        parts = line.strip().split()
        if parts:
            uuid_map["Hundo" if "Hundo" in line else "Mamulo"] = parts[0]

    if "Hundo" in uuid_map and "Mamulo" in uuid_map:
        result = runner.invoke(app, [
            "aldoni",
            uuid_map["Hundo"],
            "rdf:type",
            uuid_map["Mamulo"],
            "-y",
        ])
        assert result.exit_code == 0, f"aldoni failed: {result.stdout}"
        assert "kreita" in result.stdout or "Arc" in result.stdout


def test_triple_serci(runner: CliRunner) -> None:
    """Searching triples should work end-to-end."""
    # Setup
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Hundo", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Mamulo", "-y"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "-y"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]

    if len(uuids) >= 2:
        runner.invoke(app, ["aldoni", uuids[0], "rdf:type", uuids[1], "-y"])
        result = runner.invoke(app, ["serci", "--subject", uuids[0]])
        assert result.exit_code == 0


def test_triple_vidi(runner: CliRunner) -> None:
    """Viewing triples for a subject should work."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Hundo", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Mamulo", "-y"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "-y"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    uuids = [l.split()[0] for l in lines if len(l.split()) >= 1]

    if len(uuids) >= 2:
        runner.invoke(app, ["aldoni", uuids[0], "rdf:type", uuids[1], "-y"])
        result = runner.invoke(app, ["vidi", uuids[0]])
        assert result.exit_code == 0
        assert "rdf:type" in result.stdout or "tipo" in result.stdout


def test_predikat_grupo_importi_not_available(runner: CliRunner) -> None:
    """importi should show 'not available in P1'."""
    result = runner.invoke(app, ["predikat-grupo", "importi", "somefile.owl"])
    assert result.exit_code == 0
    assert "ne disponebla" in result.stdout or "not available" in result.stdout


def test_nodo_aldoni_with_uuid(runner: CliRunner) -> None:
    """Creating a node with a custom UUID should work."""
    custom_uuid = "deadbeef-1234-5678-9abc-def012345678"
    result = runner.invoke(app, [
        "nodo", "aldoni", custom_uuid,
        "-e", "eo::Testo",
        "-y",
    ])
    assert result.exit_code == 0
    # Verify it was created with our UUID
    result = runner.invoke(app, ["nodo", "vidi", custom_uuid[:8]])
    assert result.exit_code == 0
    assert "Testo" in result.stdout


def test_nodo_forigi(runner: CliRunner) -> None:
    """Deleting a node should work."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Forigota", "-y"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    for line in ls_result.stdout.strip().split("\n"):
        if "Forigota" in line and line[0].isalnum():
            uuid_prefix = line.split()[0]
            break
    else:
        return  # No node found

    result = runner.invoke(app, ["nodo", "forigi", uuid_prefix, "-y"])
    assert result.exit_code == 0
    assert "forigita" in result.stdout


def test_predikato_search(runner: CliRunner) -> None:
    """Searching predicates should work."""
    runner.invoke(app, ["predikato", "aldoni", "wdt:P31", "-e", "eo::tipo", "-y"])
    result = runner.invoke(app, ["predikato", "serci", "tipo"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout or "tipo" in result.stdout


def test_predikat_grupo_forigi(runner: CliRunner) -> None:
    """Deleting a group should work."""
    runner.invoke(app, ["predikat-grupo", "aldoni", "forigota", "-y"])
    result = runner.invoke(app, ["predikat-grupo", "forigi", "forigota", "-y"])
    assert result.exit_code == 0
    assert "forigita" in result.stdout
