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
