"""A-semantika data layer — SQLite storage.

Schema, get_db() singleton, init_db().
"""
from __future__ import annotations

import json
import logging
import sqlite3
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
from A_semantika.data.recenzi_storage import RECENZI_SCHEMA_SQL

if TYPE_CHECKING:
    from A.data.base import SQLiteDB

logger = logging.getLogger(__name__)

_db_instance: SQLiteDB | None = None
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


# Custom datatype URIs for typed literals in the triple store.
# These are stored in the ``object_datatype`` column and enable
# RDF-compatible type discrimination without schema changes.
KATEX_DATATYPE = "https://w3id.org/autish/katex"

# Default RDF/OWL predicates seeded into every new database.
# These match the CLI shortcuts in _cli_nodo.py (--tipo, --superklaso, --ne, --invers).
# Extended with INSERT OR IGNORE so existing databases are unaffected.
DEFAULT_PREDICATES: list[dict[str, str]] = [
    {"predicate_id": "rdf:type",              "source": "rdf",    "etikedoj": '{"eo": "tipo"}'},
    {"predicate_id": "rdfs:subClassOf",        "source": "rdfs",  "etikedoj": '{"eo": "subklaso"}'},
    {"predicate_id": "owl:disjointWith",       "source": "owl",   "etikedoj": '{"eo": "disjunkcio"}'},
    {"predicate_id": "owl:inverseOf",          "source": "owl",   "etikedoj": '{"eo": "inverso"}'},
    # File attachment metadata predicates (Issue #75)
    {"predicate_id": ":hasFilePath",           "source": "manual", "etikedoj": '{"eo": "dosiero-loko"}'},
    {"predicate_id": ":hasFileMime",           "source": "manual", "etikedoj": '{"eo": "MIME-tipo"}'},
    {"predicate_id": ":hasFileSize",           "source": "manual", "etikedoj": '{"eo": "grandeco"}'},
    {"predicate_id": ":hasFileSource",         "source": "manual", "etikedoj": '{"eo": "fontindiko"}'},
    # Unit ontology predicates (Issue #77)
    {"predicate_id": ":hasNumerator",          "source": "manual", "etikedoj": '{"eo": "havas numeratoron"}'},
    {"predicate_id": ":hasDenominator",        "source": "manual", "etikedoj": '{"eo": "havas denominatoron"}'},
    {"predicate_id": ":hasBase",               "source": "manual", "etikedoj": '{"eo": "havas bazon"}'},
    {"predicate_id": ":hasExponent",           "source": "manual", "etikedoj": '{"eo": "havas eksponenton"}'},
    {"predicate_id": ":hasTerm1",              "source": "manual", "etikedoj": '{"eo": "havas terminon 1"}'},
    {"predicate_id": ":hasTerm2",              "source": "manual", "etikedoj": '{"eo": "havas terminon 2"}'},
    {"predicate_id": ":multiplier",            "source": "manual", "etikedoj": '{"eo": "multiplikilo"}'},
    {"predicate_id": ":offset",                "source": "manual", "etikedoj": '{"eo": "ofseto"}'},
    {"predicate_id": ":ucumCode",              "source": "manual", "etikedoj": '{"eo": "UCUM-kodo"}'},
    {"predicate_id": ":symbol",                "source": "manual", "etikedoj": '{"eo": "simbolo"}'},
    {"predicate_id": ":alternativeSymbol",     "source": "manual", "etikedoj": '{"eo": "alternativa simbolo"}'},
    {"predicate_id": ":unitPrefix",            "source": "manual", "etikedoj": '{"eo": "unu-prefikso"}'},
    # RDF reification predicates (Issue: provo)
    {"predicate_id": "rdf:subject",            "source": "rdf",    "etikedoj": '{"eo": "subjekto"}'},
    {"predicate_id": "rdf:predicate",          "source": "rdf",    "etikedoj": '{"eo": "predikato"}'},
    {"predicate_id": "rdf:object",             "source": "rdf",    "etikedoj": '{\"eo\": \"objekto\"}'},
    {"predicate_id": ":hasProof",              "source": "manual", "etikedoj": '{"eo": "havas pruvon"}'},
]


def _get_data_dir() -> Path:
    """Return the data directory for A-semantika."""
    global _DATA_DIR
    if _DATA_DIR is None:
        _DATA_DIR = data_dir() / "A-semantika"
    return _DATA_DIR


def get_db() -> "SQLiteDB":
    """Return the singleton SQLiteDB instance (WAL mode, FK enforced).

    Uses :func:`A.data.base.open_healthy_db` for health check, auto-repair,
    and backup before connecting.  If the database is corrupted and cannot
    be repaired, raises ``RuntimeError`` with guidance on restoring from
    backup.

    Initializes schema on first call.
    """
    global _db_instance
    if _db_instance is not None:
        return _db_instance

    from A.data.base import open_healthy_db

    db_path = _get_data_dir() / "semantika.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _db_instance = open_healthy_db(db_path)
    except RuntimeError:
        # open_healthy_db raises RuntimeError when health check + repair
        # both fail.  Wrap with module-specific guidance.
        _raise_corruption_error(db_path)

    try:
        init_db(_db_instance)
    except sqlite3.DatabaseError:
        logger.exception("Database initialization failed — database may be corrupted.")
        _db_instance.close()
        _db_instance = None
        _raise_corruption_error(db_path)

    return _db_instance


def _raise_corruption_error(db_path: Path) -> None:
    """Raise a user-friendly RuntimeError with backup restore guidance."""
    from A.core.backup import list_backups

    backups = list_backups("A-semantika")
    if backups:
        ts = backups[0]["timestamp"]
        msg = (
            f"semantika.db estas koruptita kaj ne povas esti riparita.\n"
            f"Restarigu de sekurkopio: A sekurkopio restaŭrigi semantika {ts}\n"
            f"\n"
            f"semantika.db is corrupted and cannot be repaired.\n"
            f"Restore from backup: A sekurkopio restaŭrigi semantika {ts}\n"
            f"\n"
            f"semantika.db est corrompue et ne peut pas être réparée.\n"
            f"Restaurer depuis la sauvegarde : A sekurkopio restaŭrigi semantika {ts}\n"
        )
    else:
        msg = (
            f"semantika.db estas koruptita kaj ne povas esti riparita.\n"
            f"Neniuj sekurkopioj trovitaj. Forigu la dosieron kaj rekomencu:\n"
            f"  rm -f {db_path}*  # forigas .db, -wal, -shm\n"
            f"\n"
            f"semantika.db is corrupted and cannot be repaired.\n"
            f"No backups found. Delete the file and start fresh:\n"
            f"  rm -f {db_path}*  # removes .db, -wal, -shm\n"
            f"\n"
            f"semantika.db est corrompue et ne peut pas être réparée.\n"
            f"Aucune sauvegarde trouvée. Supprimez le fichier et recommencez :\n"
            f"  rm -f {db_path}*  # supprime .db, -wal, -shm\n"
        )
    raise RuntimeError(msg)


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


def _seed_default_unit_types(db: "SQLiteDB") -> bool:
    """Seed unit type nodes and their ``rdf:type`` triples.

    Uses INSERT OR IGNORE so that repeated calls are no-ops.

    Returns:
        True if any new nodes were inserted, False otherwise.
    """
    from A_semantika._unit_seed_data import UNIT_TYPE_NODES

    # Check how many type nodes already exist
    type_ids = [n["node_id"] for n in UNIT_TYPE_NODES]
    existing = {
        r["node_id"]
        for r in db.execute(
            "SELECT node_id FROM nodes WHERE node_id IN "
            f"({','.join('?' * len(type_ids))})",
            tuple(type_ids),
        )
    }
    new_count = sum(1 for n in UNIT_TYPE_NODES if n["node_id"] not in existing)
    if new_count == 0:
        return False

    now_iso = now()
    for node in UNIT_TYPE_NODES:
        etikedoj = json.dumps(node["etikedoj"])
        db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (node["node_id"], etikedoj, now_iso, now_iso),
        )
        # Add rdf:type triple
        parent = node["parent_type"]
        if parent:
            db.execute(
                "INSERT OR IGNORE INTO triples "
                "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
                "VALUES (?, 'rdf:type', ?, 'uri', ?)",
                (node["node_id"], parent, now_iso),
            )
        # Also add alternative type if specified (e.g. PrefixedUnit is also SingularUnit)
        also = node.get("also_type")
        if also:
            db.execute(
                "INSERT OR IGNORE INTO triples "
                "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
                "VALUES (?, 'rdf:type', ?, 'uri', ?)",
                (node["node_id"], also, now_iso),
            )
    return new_count > 0


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

    # Seed unit type nodes (Issue #77)
    _seed_default_unit_types(db)

    # Seed rdf:Statement node for reification proofs (provo)
    db.execute(
        "INSERT OR IGNORE INTO nodes (node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
        "VALUES ('rdf:Statement', '{\"eo\": \"Aserto\", \"en\": \"Statement\"}', 'Aserto Statement', '{}', '', ?, ?)",
        (now(), now()),
    )

    # Recenzi (interactive review) tables (Issue #71)
    for statement in RECENZI_SCHEMA_SQL.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            db.execute(stmt)

    # Rebuild nodes FTS index to fix stale entries from the pre-fix
    # update()/update_node_id() order-of-operations bug.
    rebuild_nodes_fts(db)


def close_db() -> None:
    """Close the database connection and reset singleton."""
    global _db_instance
    if _db_instance is not None:
        _db_instance.close()
    _db_instance = None


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
