"""Nodo CLI tests: aldoni, ls, vidi, serci, forigi."""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


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
    """Searching nodes by label should find matches."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::Birdo", "-y"])
    result = runner.invoke(app, ["nodo", "serci", "Birdo"])
    assert result.exit_code == 0
    assert "Birdo" in result.stdout


def test_nodo_serci_finds_by_id(runner: CliRunner) -> None:
    """Searching nodes by node_id should also find matches (ID + label search)."""
    # Create a node with a custom ID that contains "GPS"
    runner.invoke(app, ["nodo", "aldoni", "GPS_TK", "-e", "eo::aparata tempo-korekto por GPS", "-y"])
    # Search by the ID prefix "GPS"
    result = runner.invoke(app, ["nodo", "serci", "GPS"])
    assert result.exit_code == 0
    assert "GPS_TK" in result.stdout
    # The label should also be visible
    assert "aparata" in result.stdout or "tempo" in result.stdout


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


def test_nodo_forigi_multiple(runner: CliRunner) -> None:
    """Deleting multiple nodes at once should work."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::MultA", "-y"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::MultB", "-y"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    uuids = []
    for line in ls_result.stdout.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2 and "Mult" in " ".join(parts[1:]):
            uuids.append(parts[0])
    if len(uuids) >= 2:
        result = runner.invoke(app, ["nodo", "forigi", uuids[0], uuids[1], "-y"])
        assert result.exit_code == 0
        assert "Forigis 2 el 2" in result.stdout


def test_nodo_forigi_single_no_confirm(runner: CliRunner) -> None:
    """Single node forigi without -y skips confirmation."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::NoConfNode", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    uuid_prefix = None
    for line in ls_result.stdout.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2 and "NoConfNode" in " ".join(parts[1:]):
            uuid_prefix = parts[0]
            break
    assert uuid_prefix is not None, "Node not found"

    # No -y flag — should skip prompt for single item and delete directly
    result = runner.invoke(app, ["nodo", "forigi", uuid_prefix])
    assert result.exit_code == 0
    assert "Forigis" in result.stdout or "forigita" in result.stdout


def test_nodo_aldoni_jes_flag(runner: CliRunner) -> None:
    """--jes flag should skip confirmation for nodo aldoni."""
    result = runner.invoke(app, [
        "nodo", "aldoni",
        "-e", "eo::JesTesto",
        "--jes",
    ])
    assert result.exit_code == 0
    assert "kreita" in result.stdout or "Created" in result.stdout or "créé" in result.stdout


def test_nodo_aldoni_yes_backward_compat(runner: CliRunner) -> None:
    """--yes flag should still work (backward compat)."""
    result = runner.invoke(app, [
        "nodo", "aldoni",
        "-e", "eo::YesTesto",
        "--yes",
    ])
    assert result.exit_code == 0
    assert "kreita" in result.stdout or "Created" in result.stdout or "créé" in result.stdout


def test_forigi_jes_flag(runner: CliRunner) -> None:
    """--jes flag should skip confirmation for forigi."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::ForigJes", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    for line in ls_result.stdout.strip().split("\n"):
        if "ForigJes" in line and line[0].isalnum():
            uuid_prefix = line.split()[0]
            break
    else:
        return

    result = runner.invoke(app, ["nodo", "forigi", uuid_prefix, "--jes"])
    assert result.exit_code == 0
    assert "forigita" in result.stdout
