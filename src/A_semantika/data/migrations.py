"""Database migration functions for A-semantika schema evolution.

Each function handles a specific schema upgrade path.
Safe to call repeatedly (idempotent).
"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from A import warning as _warning

if TYPE_CHECKING:
    from A.data.base import SQLiteDB


def migrate_nodes_uuid_to_node_id(db: "SQLiteDB") -> None:
    """Migrate existing databases from old 'uuid' column to 'node_id'.

    The ``CREATE TABLE IF NOT EXISTS`` in SCHEMA_SQL does not alter
    existing tables, so databases created before the 19be0ff commit
    (``feat: rename nodes.uuid to node_id for human-readable IDs``)
    still have ``uuid`` as the primary key column.

    This migration:
    1. Drops the old ``nodes_fts`` FTS5 virtual table (it references the
       old column name; rebuilt by ``NodeService._ensure_fts``).
    2. Renames ``uuid`` → ``node_id`` on the ``nodes`` table.
    3. Renames ``uuid`` → ``node_id`` on the ``nodes_rubujo`` trash table
       if it exists.

    Safe to call on already-migrated databases (no-op when ``node_id``
    column already exists).
    """
    # Check current columns of the nodes table
    try:
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(nodes)")
        }
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        # Table may not exist yet during initial DB setup — safe to skip
        return

    if "node_id" in columns:
        # Already migrated (either new schema or previous run)
        return

    if "uuid" not in columns:
        # Unexpected — neither column exists; skip
        return

    # ── Step 1: Drop the old FTS5 virtual table ──────────────────────
    # The old FTS5 table referenced uuid, but the renamed content table
    # now uses node_id.  DROP + recreate avoids content sync issues.
    # NodeService._ensure_fts will recreate it with the correct schema.
    db.execute("DROP TABLE IF EXISTS nodes_fts")

    # ── Step 2: Rename uuid → node_id on main table ─────────────────
    db.execute("ALTER TABLE nodes RENAME COLUMN uuid TO node_id")

    # ── Step 3: Rename uuid → node_id on trash table if it exists ──
    try:
        trash_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(nodes_rubujo)")
        }
        if "uuid" in trash_columns and "node_id" not in trash_columns:
            db.execute("ALTER TABLE nodes_rubujo RENAME COLUMN uuid TO node_id")
        elif "uuid" in trash_columns and "node_id" in trash_columns:
            # Edge case: _ensure_trash_table column sync added node_id
            # alongside uuid.  Drop the orphaned uuid column.
            db.execute("ALTER TABLE nodes_rubujo DROP COLUMN uuid")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        # Trash table may not exist (no nodes ever deleted) — safe
        _warning("Trash table not found during uuid→node_id migration; skipping.")


def migrate_predicates_uuid_to_predicate_id(db: "SQLiteDB") -> None:
    """Migrate existing databases from uuid PK to predicate_id PK,
    and from legacy flat columns (label_en/label_eo/priskribo) to
    JSON columns (etikedoj/priskriboj).

    The predicates schema evolved through three states:

    | State | PK | Label cols |
    |-------|----|------------|
    | 590d9b1 (original) | ``uuid`` | ``label_en``, ``label_eo``, ``priskribo`` |
    | 035a4f5 | ``uuid`` | ``etikedoj`` (JSON), ``priskriboj`` (JSON) |
    | current | ``predicate_id`` | ``etikedoj`` (JSON), ``priskriboj`` (JSON) |

    ``CREATE TABLE IF NOT EXISTS`` was used at every step, so databases
    created at any earlier state still have the old column layout.
    This migration handles all three → current.
    """
    try:
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(predicates)")
        }
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return  # Table may not exist yet during initial DB setup

    if "uuid" not in columns:
        return  # Already migrated or new schema

    # Detect which label column layout the old table has
    has_legacy_labels = "label_eo" in columns
    has_json_labels = "etikedoj" in columns

    # ── Step 1: Recreate table with predicate_id PK + JSON labels ──
    # Drop leftovers from a previous partial migration run.
    db.execute("DROP TABLE IF EXISTS predicates_new")
    db.execute("""
        CREATE TABLE predicates_new (
            predicate_id  TEXT PRIMARY KEY,
            source        TEXT NOT NULL DEFAULT 'manual',
            etikedoj      TEXT NOT NULL DEFAULT '{}',
            priskriboj    TEXT NOT NULL DEFAULT '{}',
            aliases       TEXT NOT NULL DEFAULT '[]',
            kreita_je     TEXT NOT NULL,
            modifita_je   TEXT NOT NULL
        )
    """)

    # Step 2: Copy data — different SELECT depending on source layout
    if has_legacy_labels:
        # Legacy labels: flatten label_eo/label_en/priskribo into JSON
        # Use SQLite json_object to build etikedoj/priskriboj dicts.
        # CASE handles NULL/empty values gracefully.
        db.execute("""
            INSERT INTO predicates_new
                (predicate_id, source,
                 etikedoj, priskriboj,
                 aliases, kreita_je, modifita_je)
            SELECT
                predicate_id,
                source,
                CASE
                    WHEN label_eo IS NOT NULL AND label_eo != ''
                         AND label_en IS NOT NULL AND label_en != ''
                    THEN json_object('eo', label_eo, 'en', label_en)
                    WHEN label_eo IS NOT NULL AND label_eo != ''
                    THEN json_object('eo', label_eo)
                    WHEN label_en IS NOT NULL AND label_en != ''
                    THEN json_object('en', label_en)
                    ELSE '{}'
                END,
                CASE
                    WHEN priskribo IS NOT NULL AND priskribo != ''
                    THEN json_object('eo', priskribo)
                    ELSE '{}'
                END,
                aliases,
                kreita_je,
                modifita_je
            FROM predicates
        """)
    elif has_json_labels:
        # Already has JSON labels — direct copy
        db.execute("""
            INSERT INTO predicates_new
                (predicate_id, source, etikedoj, priskriboj,
                 aliases, kreita_je, modifita_je)
            SELECT predicate_id, source, etikedoj, priskriboj,
                   aliases, kreita_je, modifita_je
            FROM predicates
        """)
    else:
        # Fallback — no known label columns (unlikely)
        db.execute("""
            INSERT INTO predicates_new
                (predicate_id, source, etikedoj, priskriboj,
                 aliases, kreita_je, modifita_je)
            SELECT predicate_id, source, '{}', '{}',
                   aliases, kreita_je, modifita_je
            FROM predicates
        """)

    # Step 3: Swap tables — temporarily disable FK enforcement since
    # triples and predicate_group_members reference predicates(predicate_id).
    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.execute("DROP TABLE predicates")
        db.execute("ALTER TABLE predicates_new RENAME TO predicates")
    finally:
        db.execute("PRAGMA foreign_keys = ON")

    # ── Step 4: Migrate trash table if it exists ───────────────────
    try:
        trash_cols = {
            row["name"]
            for row in db.execute("PRAGMA table_info(predicates_rubujo)")
        }
        if "uuid" in trash_cols:
            db.execute("DROP TABLE IF EXISTS predicates_rubujo_new")
            db.execute("""
                CREATE TABLE predicates_rubujo_new (
                    predicate_id  TEXT PRIMARY KEY,
                    source        TEXT NOT NULL DEFAULT 'manual',
                    etikedoj      TEXT NOT NULL DEFAULT '{}',
                    priskriboj    TEXT NOT NULL DEFAULT '{}',
                    aliases       TEXT NOT NULL DEFAULT '[]',
                    kreita_je     TEXT NOT NULL,
                    modifita_je   TEXT NOT NULL,
                    forigita_je   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Same label-column detection for trash table
            has_legacy_trash = "label_eo" in trash_cols
            has_json_trash = "etikedoj" in trash_cols

            if has_legacy_trash:
                db.execute("""
                    INSERT INTO predicates_rubujo_new
                        (predicate_id, source,
                         etikedoj, priskriboj,
                         aliases, kreita_je, modifita_je, forigita_je)
                    SELECT
                        predicate_id,
                        source,
                        CASE
                            WHEN label_eo IS NOT NULL AND label_eo != ''
                                 AND label_en IS NOT NULL AND label_en != ''
                            THEN json_object('eo', label_eo, 'en', label_en)
                            WHEN label_eo IS NOT NULL AND label_eo != ''
                            THEN json_object('eo', label_eo)
                            WHEN label_en IS NOT NULL AND label_en != ''
                            THEN json_object('en', label_en)
                            ELSE '{}'
                        END,
                        CASE
                            WHEN priskribo IS NOT NULL AND priskribo != ''
                            THEN json_object('eo', priskribo)
                            ELSE '{}'
                        END,
                        aliases,
                        kreita_je,
                        modifita_je,
                        forigita_je
                    FROM predicates_rubujo
                """)
            elif has_json_trash:
                db.execute("""
                    INSERT INTO predicates_rubujo_new
                        (predicate_id, source, etikedoj, priskriboj,
                         aliases, kreita_je, modifita_je, forigita_je)
                    SELECT predicate_id, source, etikedoj, priskriboj,
                           aliases, kreita_je, modifita_je, forigita_je
                    FROM predicates_rubujo
                """)
            else:
                db.execute("""
                    INSERT INTO predicates_rubujo_new
                        (predicate_id, source, etikedoj, priskriboj,
                         aliases, kreita_je, modifita_je, forigita_je)
                    SELECT predicate_id, source, '{}', '{}',
                           aliases, kreita_je, modifita_je, forigita_je
                    FROM predicates_rubujo
                """)

            db.execute("DROP TABLE predicates_rubujo")
            db.execute("ALTER TABLE predicates_rubujo_new RENAME TO predicates_rubujo")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        _warning("Trash table not found during predicates migration; skipping.")


def migrate_predicate_group_members_unique(db: "SQLiteDB") -> None:
    """Add UNIQUE(group_uuid, predicate_id) to predicate_group_members.

    SQLite does not support ALTER TABLE ADD CONSTRAINT, so we recreate
    the table. Existing rows with duplicate (group_uuid, predicate_id)
    are deduplicated (first row wins via INSERT OR IGNORE).

    Safe to call repeatedly — detects the constraint by checking the
    table's schema SQL.
    """
    try:
        # Check if UNIQUE constraint already exists on this table
        create_sql = db.execute_one(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='predicate_group_members'"
        )
        if create_sql and "UNIQUE(" in create_sql.get("sql", ""):
            return  # Already has the constraint
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        _warning("predicate_group_members table not found during UNIQUE migration; skipping.")
        return

    if not create_sql or not create_sql.get("sql"):
        # Table does not exist — nothing to migrate
        _warning("predicate_group_members table not found during UNIQUE migration (sqlite_master); skipping.")
        return

    # ── Step 1: Create new table with UNIQUE constraint ────────────
    db.execute("DROP TABLE IF EXISTS predicate_group_members_new")
    db.execute("""
        CREATE TABLE predicate_group_members_new (
            uuid            TEXT PRIMARY KEY,
            group_uuid      TEXT NOT NULL REFERENCES predicate_groups(uuid),
            predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
            kreita_je       TEXT NOT NULL,
            UNIQUE(group_uuid, predicate_id)
        )
    """)

    # ── Step 2: Copy existing data (deduplicate via INSERT OR IGNORE) ──
    db.execute("""
        INSERT OR IGNORE INTO predicate_group_members_new
            (uuid, group_uuid, predicate_id, kreita_je)
        SELECT uuid, group_uuid, predicate_id, kreita_je
        FROM predicate_group_members
    """)

    # ── Step 3: Swap tables ────────────────────────────────────────
    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.execute("DROP TABLE predicate_group_members")
        db.execute("ALTER TABLE predicate_group_members_new RENAME TO predicate_group_members")
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def migrate_predicates_fts(db: "SQLiteDB") -> None:
    """Add FTS5 support and ``label_text`` column to the predicates table.

    For databases created before the FTS migration:
    1. Adds ``label_text`` column (denormalized from ``etikedoj``)
    2. Backfills ``label_text`` for existing rows
    3. Creates ``predicates_fts`` virtual table
    4. Rebuilds FTS index

    Safe to call repeatedly (idempotent).
    """
    try:
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(predicates)")
        }
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        _warning("predicates table not found during FTS migration; skipping.")
        return

    if "label_text" not in columns:
        try:
            db.execute("ALTER TABLE predicates ADD COLUMN label_text TEXT NOT NULL DEFAULT ''")
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            _warning("Could not add label_text column during FTS migration; skipping.")
            return

    # Backfill label_text for rows where it is still empty
    db.execute("""
        UPDATE predicates SET label_text =
            CASE
                WHEN etikedoj IS NOT NULL AND etikedoj != '{}'
                THEN (
                    SELECT group_concat(value, ' ')
                    FROM json_each(etikedoj)
                    WHERE value IS NOT NULL AND value != ''
                )
                ELSE ''
            END
        WHERE label_text = '' OR label_text IS NULL
    """)

    # Drop stale FTS table if it exists (e.g., from a partial run or old schema)
    db.execute("DROP TABLE IF EXISTS predicates_fts")

    # Create fresh FTS5 virtual table matching the current predicates schema
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS predicates_fts"
        " USING fts5("
        "  predicate_id UNINDEXED,"
        "  etikedoj,"
        "  priskriboj,"
        "  aliases,"
        "  content=predicates,"
        "  content_rowid=rowid,"
        "  tokenize='unicode61'"
        ")"
    )

    # Rebuild FTS index (using standard INSERT, not FTS5 rebuild command)
    count = db.execute_one("SELECT COUNT(*) AS cnt FROM predicates_fts")
    if count and count["cnt"] == 0:
        db.execute(
            "INSERT INTO predicates_fts"
            " (rowid, predicate_id, etikedoj, priskriboj, aliases)"
            " SELECT rowid, predicate_id, etikedoj, priskriboj, aliases"
            " FROM predicates"
        )


def rebuild_nodes_fts(db: "SQLiteDB") -> None:
    """Rebuild the ``nodes_fts`` FTS5 index from current content.

    Fixes stale index entries caused by the pre-fix ``update()`` and
    ``update_node_id()`` order-of-operations bug (FTS5 ``'delete'`` ran
    *after* content-table UPDATE, so old terms could not be matched and
    remained in the index permanently).

    Silently skips if ``nodes_fts`` does not exist (e.g. first run before
    ``NodeService`` is ever instantiated).  Safe to call repeatedly.

    Uses standard ``INSERT INTO ... SELECT ...`` instead of the FTS5
    ``'rebuild'`` command, which has been observed to cause database
    corruption in WAL mode.
    """
    try:
        db.execute_one("SELECT COUNT(*) AS cnt FROM nodes_fts")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return

    # Silent rebuild — no warning/print to avoid polluting CLI output
    # (e.g. ``Turtle export`` which captures stdout).
    db.execute(
        "INSERT INTO nodes_fts (rowid, node_id, label_text, difin_text)"
        " SELECT rowid, node_id, label_text, difin_text FROM nodes"
    )
