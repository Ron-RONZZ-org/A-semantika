"""CLI tests for rubujo (trash) subcommand group."""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


def _create_node(runner: CliRunner, label: str, node_id: str | None = None) -> str:
    """Create a node and return its short ID prefix."""
    args = ["nodo", "aldoni", "-e", f"eo::{label}", "--jes"]
    if node_id:
        args.insert(2, node_id)  # Insert node_id as first positional arg
    runner.invoke(app, args)

    # Get the node ID from ls output, skipping header
    ls_result = runner.invoke(app, ["nodo", "ls"])
    for line in ls_result.stdout.strip().split("\n"):
        line = line.strip()
        if not line or "ID" in line or "Etikedo" in line or "─" in line:
            continue
        if label in line:
            return line.split()[0]
    msg = f"Could not find node with label {label}"
    raise RuntimeError(msg)


def test_rubujo_help_shows_subcommands(runner: CliRunner) -> None:
    """rubujo --help should show all subcommands."""
    result = runner.invoke(app, ["rubujo", "--help"])
    assert result.exit_code in (0, 2)
    assert "ls" in result.stdout
    assert "restaŭrigi" in result.stdout or "restauxrigi" in result.stdout
    assert "malplenigi" in result.stdout
    assert "forigi" in result.stdout


def test_rubujo_ls_empty(runner: CliRunner) -> None:
    """rubujo ls on empty trash should show 'empty' message."""
    result = runner.invoke(app, ["rubujo", "ls"])
    assert result.exit_code == 0
    assert "malplena" in result.stdout.lower() or "empty" in result.stdout.lower()


def test_rubujo_crud_cycle(runner: CliRunner) -> None:
    """Full cycle: create -> delete -> verify trash -> restore -> verify back."""
    node_id = _create_node(runner, "RubujoCycle", "rubujocycletest")

    # Delete it
    r = runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])
    assert r.exit_code == 0

    # Verify in trash
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert node_id in trash_result.stdout

    # Restore
    r = runner.invoke(app, ["rubujo", "restauxrigi", node_id])
    assert r.exit_code == 0
    assert "restarigita" in r.stdout.lower() or "restored" in r.stdout.lower()

    # Verify back in nodes
    ls_result = runner.invoke(app, ["nodo", "ls"])
    assert node_id in ls_result.stdout

    # Delete again
    runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])

    # Permanently delete from trash
    r = runner.invoke(app, ["rubujo", "forigi", node_id, "-y"])
    assert r.exit_code == 0
    assert "permanente forigita" in r.stdout.lower() or "permanently deleted" in r.stdout.lower()

    # Should not be in trash anymore
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert node_id not in trash_result.stdout


def test_rubujo_empty_trash(runner: CliRunner) -> None:
    """malplenigi should empty the trash."""
    node_id = _create_node(runner, "RubujoEmpty", "rubujoemptytest")

    # Delete it
    runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])

    # Verify node is in trash
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert node_id in trash_result.stdout

    # Empty trash
    result = runner.invoke(app, ["rubujo", "malplenigi", "-y"])
    assert result.exit_code == 0
    assert "malplenigita" in result.stdout.lower() or "emptied" in result.stdout.lower()

    # Trash should now be empty
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert "malplena" in trash_result.stdout.lower() or "empty" in trash_result.stdout.lower()
