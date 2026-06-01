"""A-semantika data layer — SQLite storage.

Schema, get_db() singleton, init_db().
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from A.core.paths import data_dir
from A.core.backup_targets import BackupTarget
from A_semantika.data.migrations import (
    migrate_nodes_uuid_to_node_id,
    migrate_predicate_group_members_unique,
    migrate_predicates_fts,
    migrate_predicates_uuid_to_predicate_id,
    rebuild_nodes_fts,
)

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
    label_text    TEXT NOT NULL DEFAULT '',     -- denormalized from etikedoj (for FTS5)
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

-- FTS5 on predicates (external content table)
CREATE VIRTUAL TABLE IF NOT EXISTS predicates_fts USING fts5(
    predicate_id UNINDEXED,
    etikedoj,
    priskriboj,
    aliases,
    content=predicates,
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


def _seed_default_predicates(db: "SQLiteDB") -> bool:
    """Insert default RDF/OWL semantic predicates into the predicates table.

    Uses INSERT OR IGNORE so this is safe to call repeatedly:
    predicates that already exist are left untouched.

    Returns:
        True if any new predicates were inserted, False otherwise.
    """
    # Check how many default predicates already exist before seeding
    existing_ids = {
        r["predicate_id"]
        for r in db.execute(
            "SELECT predicate_id FROM predicates WHERE predicate_id IN "
            f"({','.join('?' * len(DEFAULT_PREDICATES))})",
            tuple(p["predicate_id"] for p in DEFAULT_PREDICATES),
        )
    }
    needs_seeding = any(p["predicate_id"] not in existing_ids for p in DEFAULT_PREDICATES)

    now_iso = now()
    for pred in DEFAULT_PREDICATES:
        etikedoj = pred["etikedoj"]
        # Extract label_text from etikedoj JSON
        try:
            labels = json.loads(etikedoj) if isinstance(etikedoj, str) else etikedoj
            label_text = " ".join(v for v in labels.values() if v and isinstance(v, str))
        except (json.JSONDecodeError, TypeError):
            label_text = ""
        db.execute(
            "INSERT OR IGNORE INTO predicates "
            "(predicate_id, source, etikedoj, label_text, priskriboj, aliases, kreita_je, modifita_je) "
            "VALUES (?, ?, ?, ?, '{}', '[]', ?, ?)",
            (pred["predicate_id"], pred["source"], etikedoj, label_text, now_iso, now_iso),
        )
    return needs_seeding


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
    migrate_nodes_uuid_to_node_id(db)
    migrate_predicates_uuid_to_predicate_id(db)
    migrate_predicate_group_members_unique(db)
    # Create predicates_fts table (may be needed by FTS migrations below)
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
    migrate_predicates_fts(db)
    # Seed built-in RDF/OWL predicates (must be AFTER migrations)
    seeded = _seed_default_predicates(db)
    # Only rebuild FTS index if new predicates were actually inserted.
    # Predicates inserted by PredicateService.create are already indexed;
    # seeded predicates are inserted via raw SQL and need explicit indexing.
    # Skipping the rebuild when no new rows were added avoids unnecessary
    # work on every init_db() call (e.g. read-only CLI callbacks).
    if seeded:
        db.execute("INSERT INTO predicates_fts(predicates_fts) VALUES('rebuild')")

    # Rebuild nodes FTS index to fix stale entries from the pre-fix
    # update()/update_node_id() order-of-operations bug.
    rebuild_nodes_fts(db)


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


def get_backup_targets() -> list[BackupTarget]:
    """Return backup targets for A-semantika."""
    return [
        BackupTarget(
            path=_get_data_dir() / "semantika.db",
            category="data",
            module="semantika",
            label="Semantika database",
        ),
    ]
