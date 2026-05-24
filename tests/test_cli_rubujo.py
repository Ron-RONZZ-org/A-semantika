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
    assert "restaurigi" in result.stdout
    assert "malplenigi" in result.stdout
    assert "forigi" in result.stdout


def test_rubujo_ls_empty(runner: CliRunner) -> None:
    """rubujo ls on empty trash should show 'empty' message."""
    result = runner.invoke(app, ["rubujo", "ls"])
    assert result.exit_code == 0
    assert "malplena" in result.stdout.lower() or "empty" in result.stdout.lower()


def test_rubujo_full_cycle(runner: CliRunner) -> None:
    """Full cycle: create -> delete -> verify trash -> restore -> verify back."""
    node_id = _create_node(runner, "RubujoCycle", "rubujocycletest")

    # Delete it
    r = runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])
    assert r.exit_code == 0

    # Verify in trash
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert node_id in trash_result.stdout

    # Restore using `restaurigi` (single node skips confirmation)
    r = runner.invoke(app, ["rubujo", "restaurigi", node_id])
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


def test_rubujo_restore_multiple(runner: CliRunner) -> None:
    """restaurigi should accept multiple node IDs."""
    id1 = _create_node(runner, "RestoreMulti1", "resmul1")
    id2 = _create_node(runner, "RestoreMulti2", "resmul2")

    # Delete both
    runner.invoke(app, ["nodo", "forigi", id1, "--jes"])
    runner.invoke(app, ["nodo", "forigi", id2, "--jes"])

    # Restore both (multi-item needs -y to confirm)
    r = runner.invoke(app, ["rubujo", "restaurigi", id1, id2, "-y"])
    assert r.exit_code == 0
    assert "restarigita" in r.stdout.lower() or "restored" in r.stdout.lower()

    # Verify both back
    ls_result = runner.invoke(app, ["nodo", "ls"])
    assert id1 in ls_result.stdout
    assert id2 in ls_result.stdout


def test_rubujo_permanent_delete_multiple(runner: CliRunner) -> None:
    """rubujo forigi should accept multiple node IDs."""
    id1 = _create_node(runner, "PermDelMulti1", "permdel1")
    id2 = _create_node(runner, "PermDelMulti2", "permdel2")

    # Create another 2 nodes for delete test (these will remain undeleted)
    _create_node(runner, "Survivor", "survivor1")

    # Delete both
    runner.invoke(app, ["nodo", "forigi", id1, "--jes"])
    runner.invoke(app, ["nodo", "forigi", id2, "--jes"])

    # Permanently delete both (multi-item needs -y to confirm)
    r = runner.invoke(app, ["rubujo", "forigi", id1, id2, "-y"])
    assert r.exit_code == 0
    # Check for either the per-item message or batch summary
    assert "forigita" in r.stdout.lower() or "deleted" in r.stdout.lower()

    # Trash should be empty (the 2 nodes are gone, the survivor was not deleted)
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    # Only survivor should remain
    assert "permdel" not in trash_result.stdout


def test_rubujo_empty_trash(runner: CliRunner) -> None:
    """malplenigi should empty the trash with warning and confirmation."""
    node_id = _create_node(runner, "RubujoEmpty", "rubujoemptytest")

    # Delete it
    runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])

    # Verify node is in trash
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert node_id in trash_result.stdout

    # malplenigi should show warning + entry list
    r = runner.invoke(app, ["rubujo", "malplenigi", "-y"])
    assert r.exit_code == 0
    assert "malplenigita" in r.stdout.lower() or "emptied" in r.stdout.lower()

    # Trash should now be empty
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert "malplena" in trash_result.stdout.lower() or "empty" in trash_result.stdout.lower()


def test_rubujo_empty_trash_with_days(runner: CliRunner) -> None:
    """malplenigi --days should filter by age. Fresh items survive 1-day cutoff."""
    node_id = _create_node(runner, "RubujoDays", "rubujodaystest")

    # Delete it
    runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])

    # --days 1 means items older than 1 day — a freshly deleted item should
    # NOT be affected since it was just created.
    r = runner.invoke(app, ["rubujo", "malplenigi", "-d", "1", "-y"])
    assert r.exit_code == 0
    assert "Neniuj nodoj" in r.stdout or "No nodes" in r.stdout

    # The freshly deleted item should still be in trash
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert node_id in trash_result.stdout

    # Now empty all trash without filter
    r = runner.invoke(app, ["rubujo", "malplenigi", "-y"])
    assert r.exit_code == 0
    assert "malplenigita" in r.stdout.lower() or "emptied" in r.stdout.lower()

    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert "malplena" in trash_result.stdout.lower() or "empty" in trash_result.stdout.lower()


def test_rubujo_deprecated_aliases(runner: CliRunner) -> None:
    """Deprecated aliases restauxrigi/restaŭrigi should work with warning."""
    node_id = _create_node(runner, "DepAlias", "depaliastest")

    # Delete
    runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])

    # Try deprecation alias (need -y because new batch_restore shows confirm)
    r = runner.invoke(app, ["rubujo", "restauxrigi", node_id, "-y"])
    assert r.exit_code == 0
    assert "malrekomendita" in r.stdout.lower() or "deprecated" in r.stdout.lower()
    # Also verify it actually restored
    ls_result = runner.invoke(app, ["nodo", "ls"])
    assert node_id in ls_result.stdout
