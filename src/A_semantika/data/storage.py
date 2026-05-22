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
    uuid        TEXT PRIMARY KEY,
    etikedoj    TEXT NOT NULL DEFAULT '{}',
    label_text  TEXT NOT NULL DEFAULT '',
    difinoj     TEXT NOT NULL DEFAULT '{}',
    difin_text  TEXT NOT NULL DEFAULT '',
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);

-- Predicates: semantic properties
CREATE TABLE IF NOT EXISTS predicates (
    uuid          TEXT PRIMARY KEY,
    predicate_id  TEXT NOT NULL UNIQUE,
    source        TEXT NOT NULL DEFAULT 'manual',
    label_en      TEXT DEFAULT '',
    label_eo      TEXT DEFAULT '',
    priskribo     TEXT DEFAULT '',
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
    kreita_je       TEXT NOT NULL
);

-- Triples: core semantic arcs (subject-predicate-object)
CREATE TABLE IF NOT EXISTS triples (
    subject_uuid    TEXT NOT NULL REFERENCES nodes(uuid),
    predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
    object_type     TEXT NOT NULL DEFAULT 'uri',
    object_value    TEXT NOT NULL,
    object_lang     TEXT DEFAULT NULL,
    object_datatype TEXT DEFAULT NULL,
    object_unit     TEXT DEFAULT NULL,
    object_node_uuid TEXT GENERATED ALWAYS AS (
        CASE WHEN object_type='uri' THEN object_value ELSE NULL END
    ) STORED REFERENCES nodes(uuid),
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
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    uuid UNINDEXED,
    label_text,
    difin_text,
    content=nodes,
    content_rowid=rowid,
    tokenize='unicode61'
);
"""


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


def init_db(db: "SQLiteDB | None" = None) -> None:
    """Initialize the database schema.

    Safe to call multiple times (uses IF NOT EXISTS).
    """
    if db is None:
        db = get_db()
    for statement in SCHEMA_SQL.strip().split(";"):
        statement = statement.strip()
        if statement:
            db.execute(statement)


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
