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


class TestPredicateGroupMembersUniqueMigration:
    """Tests for migrate_predicate_group_members_unique()."""

    def _create_old_schema(self, db) -> None:
        """Drop and recreate predicate_group_members WITHOUT the UNIQUE constraint."""
        db.execute("DROP TABLE IF EXISTS predicate_group_members")
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.execute("""
                CREATE TABLE predicate_group_members (
                    uuid            TEXT PRIMARY KEY,
                    group_uuid      TEXT NOT NULL,
                    predicate_id    TEXT NOT NULL,
                    kreita_je       TEXT NOT NULL
                )
            """)
        finally:
            db.execute("PRAGMA foreign_keys = ON")

    def test_migration_adds_unique_constraint(self, db) -> None:
        """Migration should add UNIQUE(group_uuid, predicate_id)."""
        # First ensure the base tables exist
        db.execute("""
            INSERT OR IGNORE INTO predicate_groups (uuid, group_name, kreita_je, modifita_je)
            VALUES ('g1', 'test', 'now', 'now')
        """)
        db.execute("""
            INSERT OR IGNORE INTO predicates (predicate_id, kreita_je, modifita_je)
            VALUES ('p1', 'now', 'now')
        """)

        # Create old schema without UNIQUE
        self._create_old_schema(db)
        db.execute(
            "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, kreita_je) "
            "VALUES ('m1', 'g1', 'p1', 'now')"
        )

        # Run migration
        from A_semantika.data.migrations import migrate_predicate_group_members_unique

        migrate_predicate_group_members_unique(db)

        # Now inserting a duplicate should fail
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, kreita_je) "
                "VALUES ('m2', 'g1', 'p1', 'now')"
            )

    def test_migration_deduplicates_existing_rows(self, db) -> None:
        """Migration should deduplicate existing rows with same (group_uuid, predicate_id)."""
        db.execute("""
            INSERT OR IGNORE INTO predicate_groups (uuid, group_name, kreita_je, modifita_je)
            VALUES ('g1', 'test', 'now', 'now')
        """)
        db.execute("""
            INSERT OR IGNORE INTO predicates (predicate_id, kreita_je, modifita_je)
            VALUES ('p1', 'now', 'now')
        """)

        self._create_old_schema(db)
        # Insert two duplicates
        db.execute(
            "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, kreita_je) "
            "VALUES ('m1', 'g1', 'p1', 'now')"
        )
        db.execute(
            "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, kreita_je) "
            "VALUES ('m2', 'g1', 'p1', 'now')"
        )

        from A_semantika.data.migrations import migrate_predicate_group_members_unique

        migrate_predicate_group_members_unique(db)

        # Only one row should remain
        count = db.execute_one("SELECT COUNT(*) AS cnt FROM predicate_group_members")
        assert count is not None
        assert count["cnt"] == 1

    def test_migration_idempotent(self, db) -> None:
        """Running migration twice should be safe."""
        db.execute("""
            INSERT OR IGNORE INTO predicate_groups (uuid, group_name, kreita_je, modifita_je)
            VALUES ('g1', 'test', 'now', 'now')
        """)
        db.execute("""
            INSERT OR IGNORE INTO predicates (predicate_id, kreita_je, modifita_je)
            VALUES ('p1', 'now', 'now')
        """)

        self._create_old_schema(db)
        db.execute(
            "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, kreita_je) "
            "VALUES ('m1', 'g1', 'p1', 'now')"
        )

        from A_semantika.data.migrations import migrate_predicate_group_members_unique

        migrate_predicate_group_members_unique(db)
        # Run a second time
        migrate_predicate_group_members_unique(db)

        # Should still have the row
        count = db.execute_one("SELECT COUNT(*) AS cnt FROM predicate_group_members")
        assert count is not None
        assert count["cnt"] == 1


class TestNodesUuidMigration:
    """Tests for migrate_nodes_uuid_to_node_id()."""

    def _create_old_schema(self, db) -> None:
        """Create nodes table with old 'uuid' column."""
        db.execute("DROP TABLE IF EXISTS nodes_fts")
        db.execute("DROP TABLE IF EXISTS nodes_rubujo")
        db.execute("DROP TABLE IF EXISTS nodes")
        db.execute("""
            CREATE TABLE nodes (
                uuid        TEXT PRIMARY KEY,
                etikedoj    TEXT NOT NULL DEFAULT '{}',
                label_text  TEXT NOT NULL DEFAULT '',
                difinoj     TEXT NOT NULL DEFAULT '{}',
                difin_text  TEXT NOT NULL DEFAULT '',
                kreita_je   TEXT NOT NULL,
                modifita_je TEXT NOT NULL
            )
        """)

    def test_migration_renames_uuid_to_node_id(self, db) -> None:
        """Migration should rename uuid -> node_id."""
        self._create_old_schema(db)
        db.execute(
            "INSERT INTO nodes (uuid, kreita_je, modifita_je) "
            "VALUES ('old-uuid-001', 'now', 'now')"
        )

        from A_semantika.data.migrations import migrate_nodes_uuid_to_node_id

        migrate_nodes_uuid_to_node_id(db)

        # Verify column renamed
        columns = {r["name"] for r in db.execute("PRAGMA table_info(nodes)")}
        assert "node_id" in columns, "node_id column should exist after migration"
        assert "uuid" not in columns, "uuid column should not exist after migration"

        # Verify data preserved
        row = db.execute_one("SELECT * FROM nodes WHERE node_id = 'old-uuid-001'")
        assert row is not None

    def test_migration_preserves_label_data(self, db) -> None:
        """Migration should preserve label and definition data."""
        self._create_old_schema(db)
        db.execute(
            "INSERT INTO nodes (uuid, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES ('n1', '{\"eo\":\"Hundo\"}', 'Hundo', '{\"eo\":\"Besto\"}', 'Besto', 'now', 'now')"
        )

        from A_semantika.data.migrations import migrate_nodes_uuid_to_node_id

        migrate_nodes_uuid_to_node_id(db)

        row = db.execute_one("SELECT * FROM nodes WHERE node_id = 'n1'")
        assert row is not None
        assert row["etikedoj"] == '{"eo":"Hundo"}'
        assert row["label_text"] == "Hundo"
        assert row["difin_text"] == "Besto"

    def test_migration_idempotent(self, db) -> None:
        """Running migration twice should be safe."""
        self._create_old_schema(db)
        db.execute(
            "INSERT INTO nodes (uuid, kreita_je, modifita_je) "
            "VALUES ('n1', 'now', 'now')"
        )

        from A_semantika.data.migrations import migrate_nodes_uuid_to_node_id

        migrate_nodes_uuid_to_node_id(db)
        migrate_nodes_uuid_to_node_id(db)  # Run twice

        row = db.execute_one("SELECT * FROM nodes WHERE node_id = 'n1'")
        assert row is not None

    def test_migration_handles_already_migrated(self, db) -> None:
        """Should be no-op on already-migrated schema."""
        # Fresh schema already has node_id — migration should be safe
        from A_semantika.data.migrations import migrate_nodes_uuid_to_node_id

        migrate_nodes_uuid_to_node_id(db)

        columns = {r["name"] for r in db.execute("PRAGMA table_info(nodes)")}
        assert "node_id" in columns
        assert "uuid" not in columns


class TestPredicatesUuidMigration:
    """Tests for migrate_predicates_uuid_to_predicate_id()."""

    def _create_old_schema_flat(self, db) -> None:
        """Create predicates with original flat-label schema (uuid PK)."""
        db.execute("DROP TABLE IF EXISTS predicates_rubujo")
        db.execute("DROP TABLE IF EXISTS predicates")
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.execute("""
                CREATE TABLE predicates (
                    uuid           TEXT PRIMARY KEY,
                    predicate_id   TEXT NOT NULL,
                    source         TEXT NOT NULL DEFAULT 'manual',
                    label_eo       TEXT DEFAULT NULL,
                    label_en       TEXT DEFAULT NULL,
                    priskribo      TEXT DEFAULT NULL,
                    aliases        TEXT NOT NULL DEFAULT '[]',
                    kreita_je      TEXT NOT NULL,
                    modifita_je    TEXT NOT NULL
                )
            """)
        finally:
            db.execute("PRAGMA foreign_keys = ON")

    def _create_old_schema_json(self, db) -> None:
        """Create predicates with JSON labels but uuid PK."""
        db.execute("DROP TABLE IF EXISTS predicates_rubujo")
        db.execute("DROP TABLE IF EXISTS predicates")
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.execute("""
                CREATE TABLE predicates (
                    uuid           TEXT PRIMARY KEY,
                    predicate_id   TEXT NOT NULL,
                    source         TEXT NOT NULL DEFAULT 'manual',
                    etikedoj       TEXT NOT NULL DEFAULT '{}',
                    priskriboj     TEXT NOT NULL DEFAULT '{}',
                    aliases        TEXT NOT NULL DEFAULT '[]',
                    kreita_je      TEXT NOT NULL,
                    modifita_je    TEXT NOT NULL
                )
            """)
        finally:
            db.execute("PRAGMA foreign_keys = ON")

    def test_migration_flat_labels_to_json(self, db) -> None:
        """Legacy flat labels (label_eo/label_en) should be converted to JSON."""
        self._create_old_schema_flat(db)
        db.execute(
            "INSERT INTO predicates (uuid, predicate_id, source, label_eo, label_en, priskribo, kreita_je, modifita_je) "
            "VALUES ('u1', 'rdf:type', 'rdf', 'tipo', 'type', 'RDF-type property', 'now', 'now')"
        )

        from A_semantika.data.migrations import migrate_predicates_uuid_to_predicate_id

        migrate_predicates_uuid_to_predicate_id(db)

        # Verify new schema
        columns = {r["name"] for r in db.execute("PRAGMA table_info(predicates)")}
        assert "predicate_id" in columns
        assert "uuid" not in columns
        assert "etikedoj" in columns

        # Verify data with predicate_id PK
        row = db.execute_one(
            "SELECT * FROM predicates WHERE predicate_id = 'rdf:type'"
        )
        assert row is not None
        import json

        labels = json.loads(row["etikedoj"])
        assert labels == {"eo": "tipo", "en": "type"}
        priskriboj = json.loads(row["priskriboj"])
        assert priskriboj == {"eo": "RDF-type property"}

    def test_migration_json_labels_preserved(self, db) -> None:
        """JSON labels should be directly copied in JSON-schema variant."""
        self._create_old_schema_json(db)
        db.execute(
            "INSERT INTO predicates (uuid, predicate_id, source, etikedoj, kreita_je, modifita_je) "
            "VALUES ('u1', 'custom:prop', 'manual', '{\"eo\":\"Propraĵo\"}', 'now', 'now')"
        )

        from A_semantika.data.migrations import migrate_predicates_uuid_to_predicate_id

        migrate_predicates_uuid_to_predicate_id(db)

        row = db.execute_one(
            "SELECT * FROM predicates WHERE predicate_id = 'custom:prop'"
        )
        assert row is not None
        import json

        labels = json.loads(row["etikedoj"])
        assert labels == {"eo": "Propraĵo"}

    def test_migration_idempotent(self, db) -> None:
        """Running migration twice should be safe."""
        self._create_old_schema_flat(db)
        db.execute(
            "INSERT INTO predicates (uuid, predicate_id, source, label_eo, kreita_je, modifita_je) "
            "VALUES ('u1', 'rdf:type', 'rdf', 'tipo', 'now', 'now')"
        )

        from A_semantika.data.migrations import migrate_predicates_uuid_to_predicate_id

        migrate_predicates_uuid_to_predicate_id(db)
        migrate_predicates_uuid_to_predicate_id(db)

        row = db.execute_one(
            "SELECT * FROM predicates WHERE predicate_id = 'rdf:type'"
        )
        assert row is not None
        import json

        labels = json.loads(row["etikedoj"])
        assert labels == {"eo": "tipo"}

    def test_migration_handles_already_migrated(self, db) -> None:
        """Should be no-op on already-migrated schema."""
        from A_semantika.data.migrations import migrate_predicates_uuid_to_predicate_id

        migrate_predicates_uuid_to_predicate_id(db)

        columns = {r["name"] for r in db.execute("PRAGMA table_info(predicates)")}
        assert "predicate_id" in columns
        assert "uuid" not in columns


class TestNewSchemaHasUniqueConstraint:
    """Tests for fresh schema UNIQUE constraint on predicate_group_members."""

    def test_new_schema_has_unique_constraint(self, db) -> None:
        """Fresh schema should include UNIQUE constraint."""
        # The schema is already initialized by the isolate_db fixture
        db.execute("""
            INSERT OR IGNORE INTO predicate_groups (uuid, group_name, kreita_je, modifita_je)
            VALUES ('g1', 'test', 'now', 'now')
        """)
        db.execute("""
            INSERT OR IGNORE INTO predicates (predicate_id, kreita_je, modifita_je)
            VALUES ('p1', 'now', 'now')
        """)
        db.execute(
            "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, kreita_je) "
            "VALUES ('m1', 'g1', 'p1', 'now')"
        )

        # Second insert with same (group_uuid, predicate_id) should fail
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, kreita_je) "
                "VALUES ('m2', 'g1', 'p1', 'now')"
            )
