"""Nodo vidi definitions and ensure_predicate edge cases.

Extracted from test_edge_cases.py — TestNodoVidiDefinitions + TestEnsurePredicate.
"""
from __future__ import annotations

import pytest

from typer.testing import CliRunner

from A_semantika.cli import app


class TestNodoVidiDefinitions:
    """nodo vidi should display definitions correctly (Q2 dead code removal)."""

    def test_vidi_with_definitions(self, runner: CliRunner) -> None:
        """Node with definitions should show them."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "TestVidiDef",
            "-e", "eo::TestVidi",
            "-d", "eo::testa difino",
            "-d", "en::test definition",
            "-y",
        ])
        assert result.exit_code == 0

        result = runner.invoke(app, ["nodo", "vidi", "TestVidiDef"])
        assert result.exit_code == 0
        assert "testa difino" in result.stdout
        assert "test definition" in result.stdout

    def test_vidi_without_definitions(self, runner: CliRunner) -> None:
        """Node without definitions should not crash and show no difinoj."""
        result = runner.invoke(app, [
            "nodo", "aldoni", "TestVidiNoDef",
            "-e", "eo::NoDef",
            "-y",
        ])
        assert result.exit_code == 0

        result = runner.invoke(app, ["nodo", "vidi", "TestVidiNoDef"])
        assert result.exit_code == 0
        assert "Difinoj" not in result.stdout

    def test_vidi_default_empty_definitions(self, runner: CliRunner, node_svc) -> None:
        """Node with default empty difinoj should not crash."""
        node_svc.create({
            "node_id": "EmptyDef",
            "etikedoj": {"eo": "EmptyDef"},
        })
        result = runner.invoke(app, ["nodo", "vidi", "EmptyDef"])
        assert result.exit_code == 0
        assert "Difinoj" not in result.stdout


class TestEnsurePredicate:
    """ensure_predicate() must handle duplicate creation gracefully (Q3)."""

    def test_ensure_predicate_creates(self, pred_svc) -> None:
        """New predicate should be created and found."""
        from A_semantika._cli_helpers import ensure_predicate
        ensure_predicate(pred_svc, "custom:test", "test")
        assert pred_svc.get_by_predicate_id("custom:test") is not None

    def test_ensure_predicate_duplicate(self, pred_svc) -> None:
        """Existing predicate should not raise on second ensure."""
        from A_semantika._cli_helpers import ensure_predicate
        ensure_predicate(pred_svc, "dup:test", "test")
        # Second call should silently succeed
        ensure_predicate(pred_svc, "dup:test", "test")

    def test_ensure_predicate_raises_on_other_errors(self, pred_svc, monkeypatch) -> None:
        """Other errors (not duplicate) should be re-raised."""
        from A_semantika._cli_helpers import ensure_predicate

        def broken_create(data):
            raise ValueError("Some other error")

        monkeypatch.setattr(pred_svc, "create", broken_create)
        with pytest.raises(ValueError, match="Some other error"):
            ensure_predicate(pred_svc, "new:test", "test")
