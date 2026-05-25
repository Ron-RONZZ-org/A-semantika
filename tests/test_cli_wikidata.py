"""Wikidata integration tests (mocked)."""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


def test_predikato_serci_wikidata_flag(runner: CliRunner, monkeypatch) -> None:
    """serci with --wikidata should show merged results with source column."""
    # Pre-seed a local predicate
    runner.invoke(app, ["predikato", "aldoni", "wdt:P1082", "-e", "eo::logxantaro", "-y"])

    def mock_search(query, languages=None, timeout=10.0):
        return [
            {
                "ligilo": "wdt:P1082",
                "etikedo": "population",
                "priskribo": "number of inhabitants",
                "aliasoj": ["pop", "p1082"],
                "fonto": "wikidata",
            },
            {
                "ligilo": "wdt:P31",
                "etikedo": "instance of",
                "priskribo": "that class of which this subject is a particular example and member",
                "aliasoj": ["is a", "p31"],
                "fonto": "wikidata",
            },
        ]

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "search_properties", mock_search)

    # Search with --wikidata
    result = runner.invoke(app, ["predikato", "serci", "wdt:--wikidata"])
    # Actually run: serci with -w flag
    result = runner.invoke(app, ["predikato", "serci", "instance", "-w"])
    assert result.exit_code == 0
    # Should show local entry (wdt:P1082) + Wikidata-only entry (wdt:P31)
    assert "wdt:P31" in result.stdout
    assert "wdt:P1082" in result.stdout
    # Fonto column should be present
    assert "Fonto" in result.stdout or "Source" in result.stdout


def test_predikato_serci_wikidata_network_failure(runner: CliRunner, monkeypatch) -> None:
    """serci with --wikidata should not crash on network failure."""
    def mock_search(query, languages=None, timeout=10.0):
        raise RuntimeError("Network error")

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "search_properties", mock_search)

    # Create a local predicate
    runner.invoke(app, ["predikato", "aldoni", "wdt:P31", "-e", "eo::tipo", "-y"])

    # Search with --wikidata — should fall back gracefully
    result = runner.invoke(app, ["predikato", "serci", "tipo", "-w"])
    assert result.exit_code == 0
    assert "wdt:P31" in result.stdout


def test_predikato_serci_empty_local_no_wikidata_shows_hint(runner: CliRunner) -> None:
    """Empty local results without --wikidata should show a hint."""
    result = runner.invoke(app, ["predikato", "serci", "nonexistent"])
    assert result.exit_code == 0
    assert "Provu" in result.stdout or "Try" in result.stdout or "Essayez" in result.stdout


def test_predikato_aldoni_wikidata_auto_fetch(runner: CliRunner, monkeypatch) -> None:
    """Aldoni with a Wikidata ID should auto-fetch labels."""
    def mock_details(prop_id, languages=None, timeout=30.0):
        return {
            "id": "P31",
            "labels": {"en": "instance of", "eo": "estas ekzemplo de"},
            "descriptions": {"en": "that class of which this subject is a particular example and member"},
            "aliases": {"en": ["is a", "P31"]},
        }

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "get_property_details", mock_details)

    result = runner.invoke(app, ["predikato", "aldoni", "P31", "-y"])
    assert result.exit_code == 0
    assert "kreita" in result.stdout or "Created" in result.stdout or "créé" in result.stdout

    # Verify labels were auto-fetched
    result = runner.invoke(app, ["predikato", "vidi", "wdt:P31"])
    assert result.exit_code == 0
    assert "estas ekzemplo de" in result.stdout
    assert "instance of" in result.stdout
    assert "wikidata" in result.stdout.lower()


def test_predikato_aldoni_wikidata_manual_override(runner: CliRunner, monkeypatch) -> None:
    """User-provided labels should override auto-fetched values."""
    def mock_details(prop_id, languages=None, timeout=30.0):
        return {
            "id": "P31",
            "labels": {"en": "instance of", "eo": "estas ekzemplo de"},
            "descriptions": {"en": "default description"},
            "aliases": {"en": ["is a", "P31"]},
        }

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "get_property_details", mock_details)

    result = runner.invoke(app, [
        "predikato", "aldoni", "P31",
        "-e", "eo::tipo",
        "-y",
    ])
    assert result.exit_code == 0

    result = runner.invoke(app, ["predikato", "vidi", "wdt:P31"])
    assert result.exit_code == 0
    # User override should take precedence
    assert "tipo" in result.stdout
    # Auto-fetched en label should still be present (not overridden)
    assert "instance of" in result.stdout


def test_predikato_aldoni_wikidata_network_failure(runner: CliRunner, monkeypatch) -> None:
    """Aldoni with Wikidata ID should not crash on network failure."""
    def mock_details(prop_id, languages=None, timeout=30.0):
        raise RuntimeError("Network error")

    import A_semantika._wikidata_helper as wh
    monkeypatch.setattr(wh, "get_property_details", mock_details)

    # Should still create the predicate with manual mode
    result = runner.invoke(app, [
        "predikato", "aldoni", "P31",
        "-e", "eo::tipo",
        "-y",
    ])
    assert result.exit_code == 0

    # Verify it was created with manual data
    result = runner.invoke(app, ["predikato", "vidi", "wdt:P31"])
    assert result.exit_code == 0
    assert "tipo" in result.stdout


def test_predikato_aldoni_non_wikidata_unchanged(runner: CliRunner) -> None:
    """Non-Wikidata IDs should not trigger auto-fetch.

    Uses a non-seeded predicate (ex:testType) to avoid conflict with
    DEFAULT_PREDICATES in storage.py.
    """
    result = runner.invoke(app, [
        "predikato", "aldoni", "ex:testType",
        "-e", "eo::testa tipo",
        "-y",
    ])
    assert result.exit_code == 0

    result = runner.invoke(app, ["predikato", "vidi", "ex:testType"])
    assert result.exit_code == 0
    assert "testa" in result.stdout
    assert "manual" in result.stdout or "fonto" in result.stdout
