"""PredicateService — CRUDService subclass for predicate management.

Predicates are lightweight metadata (no undo/trash needed).
Stores multilingual labels/descriptions as JSON columns, matching
the nodes pattern (etikedoj / priskriboj).

Uses predicate_id (content-based identifier like wdt:P31) as PK,
not a synthetic uuid — follows RDF convention where predicates
are identified by their URI/ID, not by an artifact.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from A.core.service import CRUDService

logger = logging.getLogger(__name__)
from A_semantika._constants import FTS5_KEYWORDS as _FTS5_KEYWORDS
from A_semantika._node_helpers import extract_label_text
from A_semantika.data.storage import label_from_json, now


class AmbiguousPredicateError(ValueError):
    """Raised when a predicate ID prefix matches multiple predicates."""
    pass


def _ensure_json(val: Any) -> str:
    """Serialize a dict to JSON, or return as-is if already a string."""
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


def _label_from_etikedoj(etikedoj: str | dict, langs: tuple[str, ...] = ("eo", "en")) -> str:
    """Extract a single display label from etikedoj JSON.

    Delegates to ``storage.label_from_json`` for the canonical implementation.
    """
    return label_from_json(etikedoj, langs)


class PredicateService(CRUDService):
    """Service for managing semantic predicates.

    No undo/trash (predicates are lightweight metadata).
    Uses FTS5 for full-text search on etikedoj and priskriboj,
    falling back to LIKE on predicate_id + JSON text fields.
    """

    def __init__(self, db: Any) -> None:
        super().__init__(
            db=db,
            table="predicates",
            undo_size=0,
        )

    def _ensure_fts(self) -> bool:
        """Create FTS5 virtual table for predicates if not exists.

        Returns ``True`` if FTS is usable, ``False`` if FTS is
        irreparably broken (LIKE-only mode).

        If the virtual table or its shadow tables are corrupted,
        attempts to purge and recreate them.  If the content table
        has data, attempts to rebuild the index.
        """
        # Check if the virtual table exists in sqlite_master.
        vt_entry = self.db.execute_one(
            "SELECT name FROM sqlite_master"
            " WHERE type='table' AND name='predicates_fts'"
        )
        if not vt_entry:
            try:
                self._create_fts_vt()
            except sqlite3.DatabaseError:
                logger.warning("Cannot create predicates_fts virtual table.")
                return False

        # Try to query the FTS index — if this fails, purge and recreate.
        try:
            count = self.db.execute_one(
                "SELECT COUNT(*) AS cnt FROM predicates_fts"
            )
        except sqlite3.DatabaseError:
            logger.warning(
                "predicates_fts is corrupted — purging and recreating."
            )
            try:
                self._purge_and_rebuild_fts()
            except sqlite3.DatabaseError:
                logger.error("Cannot recreate predicates_fts — LIKE only.")
                return False
            return True  # Rebuild succeeded or FTS is empty

        if count and count["cnt"] == 0:
            self._populate_predicates_fts()

        return True

    def _purge_and_rebuild_fts(self) -> None:
        """Drop a corrupted predicates_fts and recreate from scratch.

        1. Drops all FTS5 shadow tables directly (real tables).
        2. Tries ``DROP TABLE IF EXISTS`` on the virtual table.
        3. If the VT entry cannot be removed via normal DDL (because
           xConnect fails even with shadow tables gone), falls back
           to ``PRAGMA writable_schema`` to clear ``sqlite_master``.
        4. Creates a fresh FTS5 virtual table.
        5. Rebuilds the index from the predicates content table.
        """
        _SHADOW = [
            "predicates_fts_data",
            "predicates_fts_idx",
            "predicates_fts_docsize",
            "predicates_fts_config",
            "predicates_fts_content",
        ]
        for tbl in _SHADOW:
            try:
                self.db.execute(f"DROP TABLE IF EXISTS {tbl}")
            except sqlite3.DatabaseError:
                pass

        # Try dropping the virtual table (may fail if xConnect is broken).
        dropped = False
        try:
            self.db.execute("DROP TABLE IF EXISTS predicates_fts")
            dropped = True
        except sqlite3.DatabaseError:
            pass

        if not dropped:
            # Last resort: remove the broken entry from sqlite_master.
            # Use try/finally to ensure writable_schema is always reset.
            self.db.execute("PRAGMA writable_schema=ON")
            try:
                self.db.execute(
                    "DELETE FROM sqlite_master"
                    " WHERE name='predicates_fts' AND type='table'"
                )
                # Bump schema_version to force schema cache reload on
                # the *next* connection.  We then close the current
                # connection so the next execute() opens a new one
                # with a fresh schema.
                ver = self.db.execute_one("PRAGMA schema_version")
                if ver:
                    self.db.execute(
                        f"PRAGMA schema_version = {ver['schema_version'] + 1}"
                    )
            except sqlite3.DatabaseError:
                logger.error(
                    "Cannot remove corrupted predicates_fts from schema."
                )
                return
            finally:
                self.db.execute("PRAGMA writable_schema=OFF")

            # Close the current connection so the next execute()
            # creates a new one with the updated schema.
            self.db.close()

        self._create_fts_vt()
        self._populate_predicates_fts()

    def _populate_predicates_fts(self) -> None:
        """Populate predicates_fts from content table using standard INSERT.

        Uses ``INSERT INTO ... SELECT ...`` (standard SQL) instead of the
        special FTS5 ``'rebuild'`` command, which has been observed to
        cause database corruption in WAL mode.
        """
        try:
            self.db.execute(
                "INSERT INTO predicates_fts"
                " (rowid, predicate_id, etikedoj, priskriboj, aliases)"
                " SELECT rowid, predicate_id, etikedoj, priskriboj, aliases"
                " FROM predicates"
            )
        except sqlite3.DatabaseError:
            logger.warning(
                "predicates_fts population failed — using LIKE fallback."
            )

    def _create_fts_vt(self) -> None:
        """Create the predicates_fts virtual table."""
        self.db.execute(
            "CREATE VIRTUAL TABLE predicates_fts"
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

    def _remove_from_fts(self, predicate_id: str) -> bool:
        """Remove a predicate from FTS index using FTS5 'delete' command.

        .. caution::

           The caller **must** ensure the content-table row still exists
           when this method is called — the 'delete' command needs the
           ``rowid`` from the content table. Use
           :meth:`_remove_fts_by_rowid` after deletion if the row has
           already been removed.

        Returns:
            True if the row was successfully removed from the index.
            False if the row was not found or the index was rebuilt
            (caller should skip subsequent ``_index_fts``).
        """
        row = self.db.execute_one(
            "SELECT rowid FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not row or row.get("rowid") is None:
            return False
        return self._remove_fts_by_rowid(predicate_id, row["rowid"])

    def _rebuild_fts(self) -> None:
        """Rebuild the predicates FTS index from the content table.

        Uses the FTS5 ``rebuild`` command which re-reads all content
        from the external content table (``content=predicates``) and
        reconstructs the inverted index. This is the only reliable way
        to rebuild an external-content FTS5 index.
        """
        try:
            self.db.execute(
                "INSERT INTO predicates_fts(predicates_fts) VALUES('rebuild')"
            )
        except sqlite3.DatabaseError:
            # If the FTS table is too corrupted for the 'rebuild' command
            # to work (e.g. missing or broken shadow tables), fall back
            # to dropping and recreating the virtual table.
            self.db.execute("DROP TABLE IF EXISTS predicates_fts")
            self._create_fts_vt()

    def _remove_fts_by_rowid(self, predicate_id: str, rowid: int) -> bool:
        """Remove a rowid from the predicates FTS index.

        Unlike :meth:`_remove_from_fts`, this method works **after** the
        content-table row has been deleted — it only needs the saved
        rowid.

        Returns:
            True if the row was successfully removed from the index.
            False if the 'delete' failed and a full rebuild was
            performed instead (caller should skip the subsequent
            ``_index_fts`` call to avoid duplicating the row).
        """
        try:
            self.db.execute(
                "INSERT INTO predicates_fts(predicates_fts, rowid)"
                " VALUES('delete', ?)",
                (rowid,),
            )
            return True
        except sqlite3.DatabaseError as exc:
            logger.warning(
                "FTS 'delete' failed for %s (rowid=%s): %s. "
                "Rebuilding FTS index from content table.",
                predicate_id, rowid, exc,
            )
            self._rebuild_fts()
            return False

    def _index_fts(self, predicate_id: str) -> None:
        """Index a single predicate in FTS5."""
        entry = self.db.execute_one(
            "SELECT rowid, predicate_id, etikedoj, priskriboj, aliases"
            " FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not entry:
            return
        self.db.execute(
            "INSERT INTO predicates_fts(rowid, predicate_id, etikedoj, priskriboj, aliases)"
            " VALUES(?, ?, ?, ?, ?)",
            (entry["rowid"], entry["predicate_id"],
             entry.get("etikedoj", ""), entry.get("priskriboj", ""),
             entry.get("aliases", "")),
        )

    def get_by_predicate_id(self, predicate_id: str) -> dict | None:
        """Look up a predicate by its unique ID."""
        return self.db.execute_one(
            "SELECT * FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )

    def resolve_predicate_id_prefix(self, prefix: str) -> dict | None:
        """Resolve a predicate ID prefix to a full predicate dict.

        Resolution order:
        1. Exact predicate_id match (via :meth:`get_by_predicate_id`)
        2. Prefix match via LIKE on predicate_id (wildcard-escaped)
        3. If multiple prefix matches: raise :class:`AmbiguousPredicateError`
        4. If no match: return None

        Args:
            prefix: Predicate ID or prefix string.

        Returns:
            The predicate dict if exactly one match is found.

        Raises:
            AmbiguousPredicateError: If the prefix matches multiple predicates.
        """
        if not prefix:
            return None

        # Step 1: Exact match
        pred = self.get_by_predicate_id(prefix)
        if pred:
            return pred

        # Step 2: Prefix match via LIKE (wildcard-escaped)
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matches = self.db.execute(
            "SELECT * FROM predicates WHERE predicate_id LIKE ? ESCAPE '\\'",
            (f"{escaped}%",),
        )
        if not matches:
            return None
        if len(matches) > 1:
            msg = (
                f"Predicate ID prefix '{prefix}' is ambiguous "
                f"({len(matches)} matches)"
            )
            raise AmbiguousPredicateError(msg)
        return matches[0]

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a predicate with JSON-serialized etikedoj/priskriboj.

        Accepts etikedoj and priskriboj as dicts or JSON strings.
        Uses predicate_id as PK (no synthetic uuid generated).
        Updates FTS index after creation.
        """
        predicate_id = data.get("predicate_id", "")
        if not predicate_id:
            msg = "predicate_id is required"
            raise ValueError(msg)

        existing = self.get_by_predicate_id(predicate_id)
        if existing:
            msg = f"Predicate already exists: {predicate_id}"
            raise ValueError(msg)

        etikedoj = _ensure_json(data.get("etikedoj", {}))

        raw = {
            "predicate_id": predicate_id,
            "source": data.get("source", "manual"),
            "etikedoj": etikedoj,
            "label_text": extract_label_text(data.get("etikedoj", {})),
            "priskriboj": _ensure_json(data.get("priskriboj", {})),
            "aliases": _ensure_json(data.get("aliases", [])),
            "kreita_je": now(),
            "modifita_je": now(),
        }

        self.db.execute(
            """INSERT INTO predicates
               (predicate_id, source, etikedoj, label_text, priskriboj, aliases,
                kreita_je, modifita_je)
               VALUES (:predicate_id, :source, :etikedoj, :label_text,
                       :priskriboj, :aliases, :kreita_je, :modifita_je)""",
            raw,
        )
        self._index_fts(predicate_id)
        return self.get_by_predicate_id(predicate_id)

    def update(self, predicate_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a predicate.

        If etikedoj or priskriboj is a dict, it is serialized to JSON.
        Updates FTS index after modification.
        """
        old = self.get_by_predicate_id(predicate_id)
        if not old:
            msg = f"Predicate not found: {predicate_id}"
            raise ValueError(msg)

        updates = dict(data)

        if "etikedoj" in updates:
            etikedoj_val = updates["etikedoj"]
            if isinstance(etikedoj_val, dict):
                etikedoj_val = json.dumps(etikedoj_val)
            updates["etikedoj"] = etikedoj_val
            updates["label_text"] = extract_label_text(etikedoj_val)
        if "priskriboj" in updates:
            updates["priskriboj"] = _ensure_json(updates["priskriboj"])
        if "aliases" in updates:
            updates["aliases"] = _ensure_json(updates["aliases"])

        updates["modifita_je"] = now()

        set_parts = []
        params = []
        for key, val in updates.items():
            set_parts.append(f"{key} = ?")
            params.append(val)
        params.append(predicate_id)

        
        sql = f"UPDATE predicates SET {', '.join(set_parts)} WHERE predicate_id = ?"

        with self.db.transaction():
            self.db.execute(sql, params)
            # Re-index FTS (remove old, insert new)
            removed = self._remove_from_fts(predicate_id)
            if removed:
                # Only insert new if the old entry was cleanly removed.
                # If the delete failed (DatabaseError), _remove_from_fts
                # already rebuilt the entire index from the content table,
                # which includes the updated row.
                self._index_fts(predicate_id)

        return self.get_by_predicate_id(predicate_id)

    # ── Update predicate_id (rename) with manual cascade ──────────────────

    def update_predicate_id(
        self, old_id: str, new_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Rename a predicate's predicate_id, cascading to all references.

        Manual SQL UPDATEs in a single transaction to handle FK
        constraints on triples and predicate_group_members.

        Args:
            old_id: Current predicate_id.
            new_id: New predicate_id.
            data: Additional field updates (etikedoj, priskriboj, etc.).

        Returns:
            Updated predicate dict.

        Raises:
            ValueError: If old_id not found, new_id already exists, or
                PK/UNIQUE collision would occur.
        """
        old = self.get_by_predicate_id(old_id)
        if not old:
            raise ValueError(f"Predicate not found: {old_id}")

        existing = self.db.execute_one(
            "SELECT predicate_id FROM predicates WHERE predicate_id = ?", (new_id,)
        )
        if existing:
            raise ValueError(f"New predicate ID '{new_id}' already exists")

        from A_semantika._id_rename_helpers import (
            check_predicate_group_member_collision,
            check_triple_predicate_collision,
        )
        check_triple_predicate_collision(self.db, old_id, new_id)
        check_predicate_group_member_collision(self.db, old_id, new_id)

        # Build updates like update() does
        updates = dict(data)
        if "etikedoj" in updates:
            etikedoj_val = updates["etikedoj"]
            if isinstance(etikedoj_val, dict):
                etikedoj_val = json.dumps(etikedoj_val)
            updates["etikedoj"] = etikedoj_val
            updates["label_text"] = extract_label_text(etikedoj_val)
        if "priskriboj" in updates:
            updates["priskriboj"] = _ensure_json(updates["priskriboj"])
        if "aliases" in updates:
            updates["aliases"] = _ensure_json(updates["aliases"])

        updates["predicate_id"] = new_id
        updates["modifita_je"] = now()

        # Manual cascade in a single transaction
        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")
            # 1. Update the predicate's PK + fields
            set_parts = []
            params = []
            for key, val in updates.items():
                set_parts.append(f"{key} = ?")
                params.append(val)
            params.append(old_id)
            conn.execute(
                f"UPDATE predicates SET {', '.join(set_parts)} WHERE predicate_id = ?",
                params,
            )

            # 2. Update triple predicate references
            conn.execute(
                "UPDATE triples SET predicate_id = ? WHERE predicate_id = ?",
                (new_id, old_id),
            )

            # 3. Update predicate_group_member references
            conn.execute(
                "UPDATE predicate_group_members SET predicate_id = ? WHERE predicate_id = ?",
                (new_id, old_id),
            )

            # 4. Re-index FTS
            if self._fts_config:
                removed = self._remove_from_fts(old_id)
                if removed:
                    self._index_fts(new_id)

        return self.get_by_predicate_id(new_id)

    # ── Trash support ───────────────────────────────────────────────────

    def delete(self, predicate_id: str, soft: bool = True) -> None:
        """Delete a predicate.

        If soft=True, moves to trash (predicates_rubujo) instead of
        permanent deletion. Restorable via restore().
        """
        if soft:
            self._move_to_trash(predicate_id)
        else:
            saved_rowid: int | None = None
            if self._fts_config:
                row = self.db.execute_one(
                    "SELECT rowid FROM predicates WHERE predicate_id = ?",
                    (predicate_id,),
                )
                saved_rowid = row["rowid"] if row else None
            self.db.execute(
                "DELETE FROM predicates WHERE predicate_id = ?",
                (predicate_id,),
            )
            if saved_rowid is not None:
                self._remove_fts_by_rowid(predicate_id, saved_rowid)

    def _move_to_trash(self, predicate_id: str) -> None:
        """Move predicate to trash table using predicate_id column."""
        entry = self.db.execute_one(
            f"SELECT * FROM {self.table} WHERE predicate_id = ?", (predicate_id,)
        )
        if not entry:
            return

        saved_rowid: int | None = None
        if self._fts_config:
            row = self.db.execute_one(
                f"SELECT rowid FROM {self.table} WHERE predicate_id = ?",
                (predicate_id,),
            )
            saved_rowid = row["rowid"] if row else None

        entry["forigita_je"] = datetime.now(timezone.utc).isoformat()
        entry.setdefault("modifita_je", entry["forigita_je"])

        columns = list(entry.keys())
        values = list(entry.values())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT OR REPLACE INTO {self._trash_table} ({', '.join(columns)}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(sql, values)
            conn.execute(f"DELETE FROM {self.table} WHERE predicate_id = ?", (predicate_id,))

        if saved_rowid is not None:
            self._remove_fts_by_rowid(predicate_id, saved_rowid)

    def restore(self, predicate_id: str) -> dict | None:
        """Restore predicate from trash using predicate_id."""
        entry = self.db.execute_one(
            f"SELECT * FROM {self._trash_table} WHERE predicate_id = ?", (predicate_id,)
        )
        if not entry:
            return None

        entry["modifita_je"] = datetime.now(timezone.utc).isoformat()
        entry.pop("forigita_je", None)

        columns = list(entry.keys())
        values = list(entry.values())
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(insert_sql, values)
            conn.execute(f"DELETE FROM {self._trash_table} WHERE predicate_id = ?", (predicate_id,))

        if self._fts_config:
            self._index_fts(predicate_id)

        return entry

    def permanent_delete(self, predicate_id: str) -> bool:
        """Permanently delete a single entry from trash using predicate_id."""
        sql = f"DELETE FROM {self._trash_table} WHERE predicate_id = ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, (predicate_id,))
            return cursor.rowcount > 0

    def empty_trash(self, days: int = 30) -> int:
        """Permanently delete trash entries older than N days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        sql = f"DELETE FROM {self._trash_table} WHERE forigita_je < ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, (cutoff,))
            return cursor.rowcount

    def empty_all_trash(self) -> int:
        """Permanently delete ALL entries from the trash table."""
        sql = f"DELETE FROM {self._trash_table}"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql)
            return cursor.rowcount

    def get_trash(self, limit: int = 99999) -> list[dict]:
        """List entries in the trash table."""
        return self.db.execute(
            f"SELECT * FROM {self._trash_table} ORDER BY forigita_je DESC LIMIT ?",
            (limit,),
        )

    def get_trash_older_than(self, days: int, limit: int = 99999) -> list[dict]:
        """Get trash entries older than N days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return self.db.execute(
            f"SELECT * FROM {self._trash_table} WHERE forigita_je < ? ORDER BY predicate_id LIMIT ?",
            (cutoff, limit),
        )

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitize a user query string for FTS5 MATCH.

        Strips special characters that can crash FTS5, but treats
        FTS5 keywords (AND, OR, NOT) as regular content by lowercasing.

        Returns empty string if the query contains ``_`` or ``%``
        (the ``unicode61`` tokenizer treats ``_`` as a separator, so
        FTS5 cannot accurately match these; they fall through to LIKE).
        """
        if "_" in query or "%" in query:
            return ""
        safe_tokens = []
        for word in query.strip().split():
            cleaned = "".join(c for c in word if c.isalnum())
            if not cleaned:
                continue
            if cleaned.upper() in _FTS5_KEYWORDS:
                cleaned = cleaned.lower()
            safe_tokens.append(f"{cleaned}*")
        if not safe_tokens:
            return ""
        return " OR ".join(safe_tokens)

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Search predicates across predicate_id and JSON text fields.

        Uses FTS5 on etikedoj/priskriboj/aliases first, then falls
        back to LIKE on predicate_id + JSON text for edge cases.
        """
        if not query or not query.strip():
            return self.list(limit=limit)

        # Try FTS5 first (if FTS is usable)
        fts_ok = self._ensure_fts()
        fts_query = self._sanitize_fts_query(query) if fts_ok else ""
        if fts_query:
            fts_sql = """
                SELECT p.* FROM predicates p
                JOIN predicates_fts f ON p.rowid = f.rowid
                WHERE predicates_fts MATCH ?
                LIMIT ?
            """
            try:
                results = self.db.execute(fts_sql, (fts_query, limit))
            except sqlite3.DatabaseError:
                logger.warning("Predicates FTS index inconsistent — rebuilding and retrying search.")
                try:
                    self._purge_and_rebuild_fts()
                    results = self.db.execute(fts_sql, (fts_query, limit))
                except sqlite3.DatabaseError:
                    logger.error("Predicates FTS still failing after rebuild — using LIKE fallback.")
                    results = []
            if results:
                return results

        # Fallback: LIKE on predicate_id and JSON text fields (wide search)
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_sql = """
            SELECT * FROM predicates
            WHERE predicate_id LIKE ? ESCAPE '\\'
               OR label_text LIKE ? ESCAPE '\\'
            LIMIT ?
        """
        pattern = f"%{escaped}%"
        return self.db.execute(like_sql, (pattern, pattern, limit))
