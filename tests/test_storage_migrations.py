"""Tests for database migrations."""
from __future__ import annotations

import pytest


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
