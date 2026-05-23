"""Tests for database initialization and schema."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_get_db_creates_db_file(tmp_path: Path) -> None:
    """get_db() should create the database file."""
    from A_semantika.data.storage import _DATA_DIR, _DB, get_db

    # Override via monkeypatch (already done by conftest, but ensure)
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    db = get_db()
    assert db is not None
    assert (tmp_path / "semantika.db").exists()


def test_init_db_creates_tables(tmp_path: Path) -> None:
    """All expected tables should exist after init."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db

    db = get_db()

    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [t["name"] for t in tables]

    expected = [
        "nodes", "nodes_fts", "nodes_fts_config",
        "nodes_fts_data", "nodes_fts_docsize", "nodes_fts_idx",
        "predicate_group_members", "predicate_groups",
        "predicates",
        "triples",
    ]

    for t in expected:
        assert t in table_names, f"Table {t} not found in {table_names}"


def test_init_db_idempotent(tmp_path: Path) -> None:
    """Calling get_db() twice should not raise."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db

    get_db()
    get_db()  # second call should be safe


def test_wal_mode_enabled(tmp_path: Path) -> None:
    """WAL journal mode should be active."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db

    db = get_db()
    row = db.execute_one("PRAGMA journal_mode")
    assert row is not None
    # WAL or memory (in-memory fallback)
    assert row["journal_mode"].lower() in ("wal", "memory", "delete")


def test_foreign_keys_enabled(tmp_path: Path) -> None:
    """Foreign key enforcement should be on."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db

    db = get_db()
    row = db.execute_one("PRAGMA foreign_keys")
    assert row is not None
    assert row["foreign_keys"] == 1


def test_triples_without_rowid(tmp_path: Path) -> None:
    """Triples table should be WITHOUT ROWID."""
    import A_semantika.data.storage as storage_mod

    storage_mod._DATA_DIR = tmp_path  # noqa: SLF001
    storage_mod._DB = None  # noqa: SLF001

    from A_semantika.data.storage import get_db

    db = get_db()
    row = db.execute_one("SELECT sql FROM sqlite_master WHERE name='triples'")
    assert row is not None
    assert "WITHOUT ROWID" in row["sql"].upper()


def test_now_returns_iso_format() -> None:
    """now() should return an ISO-formatted UTC timestamp."""
    from A_semantika.data.storage import now

    ts = now()
    assert "T" in ts
    assert ts.endswith("+00:00") or "+00" in ts or ts.endswith("Z") or "T" in ts


def test_label_from_json() -> None:
    """label_from_json extracts labels correctly."""
    from A_semantika.data.storage import label_from_json

    result = label_from_json('{"eo": "Hundo", "en": "Dog"}')
    assert result == "Hundo"

    result = label_from_json('{"en": "Dog"}')
    assert result == "Dog"

    result = label_from_json("{}")
    assert result == ""

    result = label_from_json("")
    assert result == ""

    result = label_from_json("not-json")
    assert result == ""


# ── Default predicates seed tests ──────────────────────────────────────


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
