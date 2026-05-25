"""Tests for default predicate seeding on database init."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_default_predicates_seeded(tmp_path: Path) -> None:
    """The 4 default RDF/OWL predicates should exist after init_db()."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db

    db = get_db()
    expected_ids = ["rdf:type", "rdfs:subClassOf", "owl:disjointWith", "owl:inverseOf"]

    for pid in expected_ids:
        row = db.execute_one("SELECT * FROM predicates WHERE predicate_id = ?", (pid,))
        assert row is not None, f"Predicate {pid} not found after init_db()"
        assert row["source"] in ("rdf", "rdfs", "owl")
        assert "eo" in row["etikedoj"]


def test_default_predicates_have_correct_labels(tmp_path: Path) -> None:
    """Each default predicate should have the expected EO label."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db
    from A_semantika.data.storage import DEFAULT_PREDICATES

    db = get_db()

    for pred in DEFAULT_PREDICATES:
        row = db.execute_one(
            "SELECT etikedoj FROM predicates WHERE predicate_id = ?",
            (pred["predicate_id"],),
        )
        assert row is not None
        import json

        labels = json.loads(row["etikedoj"])
        expected = json.loads(pred["etikedoj"])
        assert labels == expected, (
            f"Label mismatch for {pred['predicate_id']}: "
            f"expected {expected}, got {labels}"
        )


def test_default_predicates_seed_idempotent(tmp_path: Path) -> None:
    """Repeated init_db() calls should not duplicate default predicates."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db, close_db

    db = get_db()
    close_db()
    storage_mod._DB = None  # noqa: SLF001

    db = get_db()  # second initialization

    rows = db.execute("SELECT predicate_id FROM predicates ORDER BY predicate_id")
    pids = [r["predicate_id"] for r in rows]
    # Each default predicate should appear exactly once
    for pid in ["rdf:type", "rdfs:subClassOf", "owl:disjointWith", "owl:inverseOf"]:
        assert pids.count(pid) == 1, f"{pid} appears {pids.count(pid)} times (expected 1)"


def test_default_predicates_existing_not_overwritten(tmp_path: Path) -> None:
    """Existing predicates with same IDs should not be overwritten by seed."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db

    db = get_db()

    # Manually insert a predicate with a modified label before seed
    db.execute(
        "INSERT OR REPLACE INTO predicates "
        "(predicate_id, source, etikedoj, priskriboj, aliases, kreita_je, modifita_je) "
        "VALUES ('rdf:type', 'manual', '{\"eo\": \"speco\"}', '{}', '[]', 'now', 'now')",
    )

    # Re-init should NOT overwrite our custom label
    from A_semantika.data.storage import init_db

    init_db(db)

    row = db.execute_one("SELECT etikedoj FROM predicates WHERE predicate_id = 'rdf:type'")
    assert row is not None
    import json

    labels = json.loads(row["etikedoj"])
    assert labels == {"eo": "speco"}, (
        f"Expected custom label 'speco' to survive re-init, got {labels}"
    )
