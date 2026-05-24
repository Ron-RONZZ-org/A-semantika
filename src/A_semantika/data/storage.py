"""A-semantika data layer — SQLite storage.

Schema, get_db() singleton, init_db().
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from A.core.paths import data_dir

if TYPE_CHECKING:
    from A.data.base import SQLiteDB

_DB: SQLiteDB | None = None
_DATA_DIR: Path | None = None

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Nodes: entities in the knowledge graph
CREATE TABLE IF NOT EXISTS nodes (
    node_id     TEXT PRIMARY KEY,
    etikedoj    TEXT NOT NULL DEFAULT '{}',
    label_text  TEXT NOT NULL DEFAULT '',
    difinoj     TEXT NOT NULL DEFAULT '{}',
    difin_text  TEXT NOT NULL DEFAULT '',
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);

-- Predicates: semantic properties
-- Uses predicate_id (content-based identifier like wdt:P31) as PK,
-- not a synthetic uuid — follows RDF convention where predicates
-- are identified by their URI/ID, not by an artifact.
-- source: 'wikidata' | 'manual' | 'owl' | 'rdfs' | 'rdf'
CREATE TABLE IF NOT EXISTS predicates (
    predicate_id  TEXT PRIMARY KEY,
    source        TEXT NOT NULL DEFAULT 'manual',
    etikedoj      TEXT NOT NULL DEFAULT '{}',
    priskriboj    TEXT NOT NULL DEFAULT '{}',
    aliases       TEXT NOT NULL DEFAULT '[]',
    kreita_je     TEXT NOT NULL,
    modifita_je   TEXT NOT NULL
);

-- Predicate groups
CREATE TABLE IF NOT EXISTS predicate_groups (
    uuid         TEXT PRIMARY KEY,
    group_name   TEXT NOT NULL UNIQUE,
    kreita_je    TEXT NOT NULL,
    modifita_je  TEXT NOT NULL
);

-- Predicate group members
CREATE TABLE IF NOT EXISTS predicate_group_members (
    uuid            TEXT PRIMARY KEY,
    group_uuid      TEXT NOT NULL REFERENCES predicate_groups(uuid),
    predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
    kreita_je       TEXT NOT NULL,
    UNIQUE(group_uuid, predicate_id)
);

-- Triples: core semantic arcs (subject-predicate-object)
CREATE TABLE IF NOT EXISTS triples (
    subject_uuid    TEXT NOT NULL REFERENCES nodes(node_id),
    predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
    object_type     TEXT NOT NULL DEFAULT 'uri',
    object_value    TEXT NOT NULL,
    object_lang     TEXT DEFAULT NULL,
    object_datatype TEXT DEFAULT NULL,
    object_unit     TEXT DEFAULT NULL,
    object_node_uuid TEXT GENERATED ALWAYS AS (
        CASE WHEN object_type='uri' THEN object_value ELSE NULL END
    ) STORED REFERENCES nodes(node_id),
    kreita_je       TEXT NOT NULL,
    PRIMARY KEY (subject_uuid, predicate_id, object_value, object_type)
) WITHOUT ROWID;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_triples_pos
    ON triples(predicate_id, object_value, subject_uuid);
CREATE INDEX IF NOT EXISTS idx_triples_osp
    ON triples(object_value, object_type, predicate_id, subject_uuid);
CREATE INDEX IF NOT EXISTS idx_pred_group_members_group
    ON predicate_group_members(group_uuid);
CREATE INDEX IF NOT EXISTS idx_pred_group_members_pred
    ON predicate_group_members(predicate_id);
CREATE INDEX IF NOT EXISTS idx_nodes_label_text
    ON nodes(label_text);

-- FTS5 on nodes (external content table)
-- Note: CRUDService manages FTS indexing manually via _index_fts/_remove_from_fts,
-- so no triggers are needed (they would conflict with CRUDService's approach).
-- Uses node_id (not uuid) since nodes table uses human-readable IDs.
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    node_id UNINDEXED,
    label_text,
    difin_text,
    content=nodes,
    content_rowid=rowid,
    tokenize='unicode61'
);
"""


# Default RDF/OWL predicates seeded into every new database.
# These match the CLI shortcuts in _cli_nodo.py (--tipo, --superklaso, --ne, --invers).
# Extended with INSERT OR IGNORE so existing databases are unaffected.
DEFAULT_PREDICATES: list[dict[str, str]] = [
    {"predicate_id": "rdf:type",        "source": "rdf",  "etikedoj": '{"eo": "tipo"}'},
    {"predicate_id": "rdfs:subClassOf",  "source": "rdfs", "etikedoj": '{"eo": "subklaso"}'},
    {"predicate_id": "owl:disjointWith", "source": "owl",  "etikedoj": '{"eo": "disjunkcio"}'},
    {"predicate_id": "owl:inverseOf",    "source": "owl",  "etikedoj": '{"eo": "inverso"}'},
]


def _get_data_dir() -> Path:
    """Return the data directory for A-semantika."""
    global _DATA_DIR
    if _DATA_DIR is None:
        _DATA_DIR = data_dir() / "A-semantika"
    return _DATA_DIR


def get_db() -> "SQLiteDB":
    """Return the singleton SQLiteDB instance (WAL mode, FK enforced).

    Initializes schema on first call.
    """
    global _DB
    if _DB is None:
        from A.data.base import SQLiteDB

        db_path = _get_data_dir() / "semantika.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _DB = SQLiteDB(db_path)
        init_db(_DB)
    return _DB


def _migrate_nodes_uuid_to_node_id(db: "SQLiteDB") -> None:
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
    except Exception:
        # Table does not exist yet — nothing to migrate
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
    except Exception:
        # Trash table may not exist (no nodes ever deleted) — safe
        pass


def _migrate_predicates_uuid_to_predicate_id(db: "SQLiteDB") -> None:
    """Migrate existing databases from uuid PK to predicate_id PK,
    and from legacy flat columns (label_en/label_eo/priskribo) to
    JSON columns (etikedoj/priskriboj).

    The predicates schema evolved through three states:

    | State | PK | Label cols |
    |-------|----|------------|
    | 590d9b1 (original) | ``uuid`` | ``label_en``, ``label_eo``, ``priskribo`` |
    | 035a4f5 | ``uuid`` | ``etikedoj`` (JSON), ``priskriboj`` (JSON) |
    | current (this commit) | ``predicate_id`` | ``etikedoj`` (JSON), ``priskriboj`` (JSON) |

    ``CREATE TABLE IF NOT EXISTS`` was used at every step, so databases
    created at any earlier state still have the old column layout.
    This migration handles all three → current.
    """
    try:
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(predicates)")
        }
    except Exception:
        return  # Table does not exist yet

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
    except Exception:
        pass  # Trash table may not exist


def _migrate_predicate_group_members_unique(db: "SQLiteDB") -> None:
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
    except Exception:
        return  # Table doesn't exist yet

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


def _seed_default_predicates(db: "SQLiteDB") -> None:
    """Insert default RDF/OWL semantic predicates into the predicates table.

    Uses INSERT OR IGNORE so this is safe to call repeatedly:
    predicates that already exist (created by _ensure_predicate in
    older versions of _cli_nodo.py) are left untouched.
    """
    now_iso = now()
    for pred in DEFAULT_PREDICATES:
        db.execute(
            "INSERT OR IGNORE INTO predicates "
            "(predicate_id, source, etikedoj, priskriboj, aliases, kreita_je, modifita_je) "
            "VALUES (?, ?, ?, '{}', '[]', ?, ?)",
            (pred["predicate_id"], pred["source"], pred["etikedoj"], now_iso, now_iso),
        )


def init_db(db: "SQLiteDB | None" = None) -> None:
    """Initialize the database schema.

    Safe to call multiple times (uses IF NOT EXISTS).
    Also runs migration for legacy databases that still have the
    ``uuid`` column (renamed to ``node_id`` in commit 19be0ff).
    """
    if db is None:
        db = get_db()
    for statement in SCHEMA_SQL.strip().split(";"):
        statement = statement.strip()
        if statement:
            db.execute(statement)
    # Run column-rename migrations for existing databases
    _migrate_nodes_uuid_to_node_id(db)
    _migrate_predicates_uuid_to_predicate_id(db)
    _migrate_predicate_group_members_unique(db)
    # Seed built-in RDF/OWL predicates (must be AFTER migrations)
    _seed_default_predicates(db)


def close_db() -> None:
    """Close the database connection and reset singleton."""
    global _DB
    if _DB is not None:
        _DB.close()
    _DB = None


def now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ---- Label helpers ----

def label_from_json(etikedoj: str, lang_fallback: tuple[str, ...] = ("eo", "en")) -> str:
    """Extract a single display label from etikedoj JSON.

    Tries language codes in order, falls back to first available.
    Returns empty string if no label found.
    """
    try:
        labels = json.loads(etikedoj) if isinstance(etikedoj, str) else etikedoj
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(labels, dict):
        return ""
    for lang in lang_fallback:
        val = labels.get(lang)
        if val and isinstance(val, str):
            return val
    # Fallback: first non-empty value
    for val in labels.values():
        if val and isinstance(val, str):
            return val
    return ""


def defn_from_json(difinoj: str, lang_fallback: tuple[str, ...] = ("eo", "en")) -> str:
    """Extract a single display definition from difinoj JSON.

    Same fallback logic as label_from_json.
    """
    return label_from_json(difinoj, lang_fallback)
