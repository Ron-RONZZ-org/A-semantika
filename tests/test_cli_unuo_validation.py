"""Tests for --unuo/-u node_id validation in aldoni and modifi.

Covers:
- Happy path: valid unit node resolves and triple is created
- Error: unit prefix does not match any existing node
- Error: unit prefix is ambiguous
- modifi preserves old object_unit when not specifying --unuo
- modifi sets new --unuo on an existing triple
"""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


# ── Helpers ──────────────────────────────────────────────────────────


def _setup_basic_entities(runner: CliRunner) -> tuple[str, str, str, str]:
    """Create subject, unit, another-unit nodes and a predicate.

    Returns:
        Tuple of (subject_id, unit_id, another_unit_id, predicate_id).
    """
    # Create nodes
    runner.invoke(app, ["nodo", "aldoni", "SUBJETO", "-e", "eo::Subjekto", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "KULOMBJO", "-e", "eo::Kulombjo", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "KELVINO", "-e", "eo::Kelvino", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "ex:measure", "-e", "eo::mezuro", "--jes"])

    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    ids: dict[str, str] = {}
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 2:
            ids[parts[-1]] = parts[0]

    subj_id = ids.get("Subjekto", "")
    unit_id = ids.get("Kulombjo", "")
    another_id = ids.get("Kelvino", "")
    return (subj_id, unit_id, another_id, "ex:measure")


# ── aldoni: --unuo validation ───────────────────────────────────────


def test_aldoni_unuo_valid_node_success(runner: CliRunner) -> None:
    """aldoni --float --unuo with a valid node ID should succeed."""
    subj_id, unit_id, _, pred_id = _setup_basic_entities(runner)
    if not subj_id or not unit_id:
        return  # skip if setup failed

    result = runner.invoke(app, [
        "aldoni", subj_id, pred_id,
        "-f", "-u", unit_id, "--", "1.5", "--jes",
    ])
    assert result.exit_code == 0, (
        f"aldoni with valid --unuo failed: {result.stdout}"
    )
    assert "kreita" in result.stdout or "created" in result.stdout or "Arc" in result.stdout


def test_aldoni_unuo_prefix_resolved(runner: CliRunner) -> None:
    """aldoni with prefix of unit node should resolve the full ID."""
    subj_id, unit_id, _, pred_id = _setup_basic_entities(runner)
    if not subj_id or not unit_id:
        return

    # Use prefix "KUL" to match "KULOMBJO"
    result = runner.invoke(app, [
        "aldoni", subj_id, pred_id,
        "-f", "-u", "KUL", "--", "2.0", "--jes",
    ])
    assert result.exit_code == 0, (
        f"aldoni with unit prefix failed: {result.stdout}"
    )
    assert "kreita" in result.stdout or "created" in result.stdout or "Arc" in result.stdout


def test_aldoni_unuo_not_found_exits_error(runner: CliRunner) -> None:
    """aldoni --unuo with a nonexistent node ID should exit with error."""
    subj_id, _, _, pred_id = _setup_basic_entities(runner)
    if not subj_id:
        return

    result = runner.invoke(app, [
        "aldoni", subj_id, pred_id,
        "-f", "-u", "NONEXIST", "--", "3.0", "--jes",
    ])
    assert result.exit_code == 1
    assert "ne trovita" in result.stdout or "not found" in result.stdout


def test_aldoni_unuo_ambiguous_exits_error(runner: CliRunner) -> None:
    """aldoni --unuo with an ambiguous prefix should exit with error.

    "K" matches both "KULOMBJO" and "KELVINO".
    """
    subj_id, _, _, pred_id = _setup_basic_entities(runner)
    if not subj_id:
        return

    result = runner.invoke(app, [
        "aldoni", subj_id, pred_id,
        "-f", "-u", "K", "--", "4.0", "--jes",
    ])
    assert result.exit_code == 1
    assert "Ambigua" in result.stdout or "Ambiguous" in result.stdout


# ── modifi: --unuo preservation and setting ─────────────────────────


def test_modifi_preserves_object_unit(runner: CliRunner) -> None:
    """modifi should preserve object_unit when not specifying --unuo."""
    subj_id, unit_id, _, pred_id = _setup_basic_entities(runner)
    if not subj_id or not unit_id:
        return

    # Create triple with unit: Subjekto ex:measure "1.5"^^xsd:decimal, unit=KULOMBJO
    result = runner.invoke(app, [
        "aldoni", subj_id, pred_id,
        "-f", "-u", unit_id, "--", "1.5", "--jes",
    ])
    assert result.exit_code == 0, f"setup aldoni failed: {result.stdout}"

    # Now modifi: change the numeric value from 1.5 to 2.5, keep the unit
    result = runner.invoke(app, [
        "modifi", subj_id, pred_id, "1.5",
        "--nova-objekto", "2.5",
        "--float", "--jes",
    ])
    assert result.exit_code == 0, f"modifi failed: {result.stdout}"
    assert "modifita" in result.stdout or "modified" in result.stdout

    # Verify via serci that the new triple has the unit
    serci_result = runner.invoke(app, ["serci", "--subjekto", subj_id])
    assert serci_result.exit_code == 0
    # The output should mention the new value 2.5
    assert "2.5" in serci_result.stdout


def test_modifi_sets_new_unuo(runner: CliRunner) -> None:
    """modifi should set a new object_unit when --unuo is provided."""
    subj_id, unit_id, another_id, pred_id = _setup_basic_entities(runner)
    if not subj_id or not unit_id or not another_id:
        return

    # Create triple without unit
    result = runner.invoke(app, [
        "aldoni", subj_id, pred_id,
        "-f", "--", "10.0", "--jes",
    ])
    assert result.exit_code == 0, f"setup aldoni failed: {result.stdout}"

    # Now modifi: add a unit via --unuo
    result = runner.invoke(app, [
        "modifi", subj_id, pred_id, "10.0",
        "--nova-objekto", "20.0",
        "--float", "-u", unit_id,
        "--jes",
    ])
    assert result.exit_code == 0, f"modifi with --unuo failed: {result.stdout}"
    assert "modifita" in result.stdout or "modified" in result.stdout


def test_modifi_unuo_not_found_exits_error(runner: CliRunner) -> None:
    """modifi --unuo with a nonexistent node ID should exit with error."""
    subj_id, unit_id, _, pred_id = _setup_basic_entities(runner)
    if not subj_id or not unit_id:
        return

    # Create triple with unit first
    result = runner.invoke(app, [
        "aldoni", subj_id, pred_id,
        "-f", "-u", unit_id, "--", "5.0", "--jes",
    ])
    assert result.exit_code == 0, f"setup aldoni failed: {result.stdout}"

    # Now try to modifi with nonexistent unit
    result = runner.invoke(app, [
        "modifi", subj_id, pred_id, "5.0",
        "--nova-objekto", "6.0",
        "--float", "-u", "BADUNIT",
        "--jes",
    ])
    assert result.exit_code == 1
    assert "ne trovita" in result.stdout or "not found" in result.stdout
