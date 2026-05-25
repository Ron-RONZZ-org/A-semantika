"""CLI tests for rubujo (trash) subcommand group."""
from __future__ import annotations

import pytest
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


def test_rubujo_empty_trash_count_accuracy(runner: CliRunner) -> None:
    """malplenigi should report the actual count from empty_trash(), not len(items)."""
    id1 = _create_node(runner, "CountAcc1", "cntacc1")
    id2 = _create_node(runner, "CountAcc2", "cntacc2")

    # Delete both
    runner.invoke(app, ["nodo", "forigi", id1, "--jes"])
    runner.invoke(app, ["nodo", "forigi", id2, "--jes"])

    # Empty trash
    r = runner.invoke(app, ["rubujo", "malplenigi", "-y"])
    assert r.exit_code == 0
    # Should report correct count
    assert "2" in r.stdout

    # Trash should be empty
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert "malplena" in trash_result.stdout.lower() or "empty" in trash_result.stdout.lower()


def test_rubujo_ls_short_node_id_no_truncation(runner: CliRunner) -> None:
    """rubujo ls should show short node IDs (< 8 chars) without truncation."""
    # Create a node with a short (5-char) human-readable ID
    runner.invoke(app, ["nodo", "aldoni", "SPACO", "-e", "eo::Spaco", "--jes"])
    runner.invoke(app, ["nodo", "forigi", "SPACO", "--jes"])

    # Check rubujo ls shows the full short ID
    r = runner.invoke(app, ["rubujo", "ls"])
    assert r.exit_code == 0
    # Should show "SPACO" not just "SPACO" - the full ID
    assert "SPACO" in r.stdout
    # SPACO is 5 chars, should NOT be truncated
    assert "SPACO" in r.stdout  # full ID visible


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


def test_rubujo_restore_interactive_confirm(runner: CliRunner) -> None:
    """restaurigi with multiple items should show confirm prompt (no -y)."""
    id1 = _create_node(runner, "RestoreConfirm1", "rescon1")
    id2 = _create_node(runner, "RestoreConfirm2", "rescon2")

    # Delete both
    runner.invoke(app, ["nodo", "forigi", id1, "--jes"])
    runner.invoke(app, ["nodo", "forigi", id2, "--jes"])

    # Restore both WITHOUT -y, confirming with "j" (default=True → [J/n])
    r = runner.invoke(app, ["rubujo", "restaurigi", id1, id2], input="j\n")
    assert r.exit_code == 0
    assert "restarigita" in r.stdout.lower() or "restored" in r.stdout.lower()

    # Verify both back
    ls_result = runner.invoke(app, ["nodo", "ls"])
    assert id1 in ls_result.stdout
    assert id2 in ls_result.stdout


def test_rubujo_restore_interactive_cancel(runner: CliRunner) -> None:
    """restaurigi with multiple items should cancel on 'n' input."""
    id1 = _create_node(runner, "RestoreCancel1", "rescan1")
    id2 = _create_node(runner, "RestoreCancel2", "rescan2")

    # Delete both
    runner.invoke(app, ["nodo", "forigi", id1, "--jes"])
    runner.invoke(app, ["nodo", "forigi", id2, "--jes"])

    # Cancel with "n" input (default=True → [J/n], so "n" cancels)
    r = runner.invoke(app, ["rubujo", "restaurigi", id1, id2], input="n\n")
    assert r.exit_code == 0
    assert "Nuligita" in r.stdout or "Cancelled" in r.stdout

    # Nodes should still be in trash (NOT restored)
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert id1 in trash_result.stdout
    assert id2 in trash_result.stdout


def test_rubujo_permanent_delete_interactive_confirm(runner: CliRunner) -> None:
    """rubujo forigi with multiple items should show confirm prompt (no -y)."""
    id1 = _create_node(runner, "PermDelInt1", "perdint1")
    id2 = _create_node(runner, "PermDelInt2", "perdint2")

    # Delete both
    runner.invoke(app, ["nodo", "forigi", id1, "--jes"])
    runner.invoke(app, ["nodo", "forigi", id2, "--jes"])

    # Permanently delete WITHOUT -y, confirming with "j" (default=False → [j/N])
    r = runner.invoke(app, ["rubujo", "forigi", id1, id2], input="j\n")
    assert r.exit_code == 0
    assert "forigita" in r.stdout.lower() or "deleted" in r.stdout.lower()

    # Should be gone from trash
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert id1 not in trash_result.stdout
    assert id2 not in trash_result.stdout


def test_rubujo_permanent_delete_interactive_cancel(runner: CliRunner) -> None:
    """rubujo forigi with multiple items should cancel on non-confirm input."""
    id1 = _create_node(runner, "PermDelIntCan1", "perdinc1")
    id2 = _create_node(runner, "PermDelIntCan2", "perdinc2")

    # Delete both
    runner.invoke(app, ["nodo", "forigi", id1, "--jes"])
    runner.invoke(app, ["nodo", "forigi", id2, "--jes"])

    # Cancel (default=False → [j/N], "n" or newline cancels)
    r = runner.invoke(app, ["rubujo", "forigi", id1, id2], input="n\n")
    assert r.exit_code == 0
    assert "Nuligita" in r.stdout or "Cancelled" in r.stdout

    # Nodes should still be in trash
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert id1 in trash_result.stdout
    assert id2 in trash_result.stdout


def test_rubujo_malplenigi_interactive_confirm(runner: CliRunner) -> None:
    """malplenigi should work via interactive confirm (no -y)."""
    node_id = _create_node(runner, "MalplenigiInt", "malpint")

    # Delete it
    runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])

    # Empty trash WITHOUT -y, confirming with "j" (default=False → [j/N])
    r = runner.invoke(app, ["rubujo", "malplenigi"], input="j\n")
    assert r.exit_code == 0
    assert "malplenigita" in r.stdout.lower() or "emptied" in r.stdout.lower()

    # Trash should be empty
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert "malplena" in trash_result.stdout.lower() or "empty" in trash_result.stdout.lower()


def test_rubujo_malplenigi_interactive_cancel(runner: CliRunner) -> None:
    """malplenigi should cancel on non-confirm input."""
    node_id = _create_node(runner, "MalplenigiCan", "malpcan")

    # Delete it
    runner.invoke(app, ["nodo", "forigi", node_id, "--jes"])

    # Cancel malplenigi (default=False → [j/N])
    r = runner.invoke(app, ["rubujo", "malplenigi"], input="n\n")
    assert r.exit_code == 0
    assert "Nuligita" in r.stdout or "Cancelled" in r.stdout

    # Node should still be in trash
    trash_result = runner.invoke(app, ["rubujo", "ls"])
    assert node_id in trash_result.stdout


# ── B3: Case‑insensitive trash lookup ─────────────────────────────────────


def test_rubujo_restore_case_insensitive(runner: CliRunner) -> None:
    """restaurigi should find trash nodes case‑insensitively (COLLATE NOCASE).

    Create a node with uppercase ID (e.g. SPACO), trash it, then restore
    using lowercase prefix. Without COLLATE NOCASE the LIKE search would
    fail to match the uppercase ID.
    """
    runner.invoke(app, ["nodo", "aldoni", "SPACO", "-e", "eo::Spaco", "--jes"])
    ls_r = runner.invoke(app, ["nodo", "ls"])
    assert "SPACO" in ls_r.stdout

    # Trash it
    r = runner.invoke(app, ["nodo", "forigi", "SPACO", "--jes"])
    assert r.exit_code == 0

    # Restore using LOWERCASE prefix — COLLATE NOCASE is required here
    r = runner.invoke(app, ["rubujo", "restaurigi", "spaco"])
    assert r.exit_code == 0
    assert "restarigita" in r.stdout.lower() or "restored" in r.stdout.lower()

    # Verify it is back
    ls_r = runner.invoke(app, ["nodo", "ls"])
    assert "SPACO" in ls_r.stdout


def test_rubujo_forigi_case_insensitive(runner: CliRunner) -> None:
    """rubujo forigi should find trash nodes case‑insensitively."""
    runner.invoke(app, ["nodo", "aldoni", "MAMULO", "-e", "eo::Mamulo", "--jes"])

    # Trash it
    runner.invoke(app, ["nodo", "forigi", "MAMULO", "--jes"])

    # Permanently delete using lowercase — must find via COLLATE NOCASE
    r = runner.invoke(app, ["rubujo", "forigi", "mamulo", "-y"])
    assert r.exit_code == 0
    assert "forigita" in r.stdout.lower() or "deleted" in r.stdout.lower()

    # Should be gone from trash
    trash_r = runner.invoke(app, ["rubujo", "ls"])
    assert "MAMULO" not in trash_r.stdout


# ── Q1: LIKE wildcard escaping in _resolve_trash_node() ──────────────────


def test_rubujo_resolve_trash_node_underscore_matched_literally(runner: CliRunner) -> None:
    """LIKE escape: underscore in node_id must match literally, not as wildcard.

    Create a node with ``test_1`` (underscore) and another with ``testX1``.
    If ``_`` is not escaped, the LIKE pattern ``test_%`` would match both.
    Verifies that only ``test_1`` is found in trash.
    """
    runner.invoke(app, ["nodo", "aldoni", "test_underscore_1", "-e", "eo::Underscore1", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "testX1", "-e", "eo::TestX1", "--jes"])

    # Trash both
    r = runner.invoke(app, ["nodo", "forigi", "test_underscore_1", "--jes"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["nodo", "forigi", "testX1", "--jes"])
    assert r.exit_code == 0

    # Now restore using prefix "test_" — must match ONLY test_underscore_1
    r = runner.invoke(app, ["rubujo", "restaurigi", "test_underscore"])
    assert r.exit_code == 0
    assert "restarigita" in r.stdout.lower() or "restored" in r.stdout.lower()

    # The other node should still be in trash
    trash_r = runner.invoke(app, ["rubujo", "ls"])
    assert "testX1" in trash_r.stdout


def test_rubujo_resolve_trash_node_percent_matched_literally(runner: CliRunner) -> None:
    """LIKE escape: percent in node_id must match literally, not as wildcard."""
    runner.invoke(app, ["nodo", "aldoni", "test%pct", "-e", "eo::PercentTest", "--jes"])

    # Trash it
    r = runner.invoke(app, ["nodo", "forigi", "test%pct", "--jes"])
    assert r.exit_code == 0

    # Restore using prefix "test%" — the % must be escaped to match literally
    r = runner.invoke(app, ["rubujo", "restaurigi", "test%pct"])
    assert r.exit_code == 0
    assert "restarigita" in r.stdout.lower() or "restored" in r.stdout.lower()

    # Verify node is restored (no longer in trash)
    trash_r = runner.invoke(app, ["rubujo", "ls"])
    assert "test%pct" not in trash_r.stdout
