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
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from A.core.service import CRUDService
from A_semantika._constants import FTS5_KEYWORDS as _FTS5_KEYWORDS
from A_semantika._node_helpers import extract_label_text
from A_semantika.data.storage import label_from_json, now


class AmbiguousPredicateError(ValueError):
    """Raised when a predicate ID prefix matches multiple predicates.

    Attributes:
        matches: List of matching predicate dicts (for interactive selection).
    """
    def __init__(self, message: str, matches: list[dict] | None = None) -> None:
        super().__init__(message)
        self.matches: list[dict] = matches or []


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

    def _ensure_fts(self) -> None:
        """Create FTS5 virtual table for predicates if not exists.

        Uses predicate_id (not uuid) to match the predicates PK.
        """
        self.db.execute(
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
        fts_count = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM predicates_fts"
        )
        pred_count = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM predicates"
        )
        # Rebuild if FTS is empty OR if counts mismatch (stale index after
        # rename/delete/restore operations that happened before the FTS
        # re-index fix in commit 9f1feff).
        needs_rebuild = (
            fts_count is None
            or fts_count["cnt"] == 0
            or (pred_count and fts_count["cnt"] != pred_count["cnt"])
        )
        if needs_rebuild:
            self.db.execute(
                "INSERT INTO predicates_fts(predicates_fts) VALUES('rebuild')"
            )

    def _remove_from_fts(self, predicate_id: str) -> None:
        """Remove a predicate from FTS index using FTS5 'delete' command.

        If the 'delete' command fails, auto-rebuilds the entire FTS index
        (following A-encik's pattern of silent auto-recovery).
        """
        row = self.db.execute_one(
            "SELECT rowid FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not row or row.get("rowid") is None:
            return
        try:
            self.db.execute(
                "INSERT INTO predicates_fts(predicates_fts, rowid)"
                " VALUES('delete', ?)",
                (row["rowid"],),
            )
        except sqlite3.DatabaseError:
            self.db.execute(
                "INSERT INTO predicates_fts(predicates_fts) VALUES('rebuild')"
            )

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
            raise AmbiguousPredicateError(msg, matches=matches)
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

        # Wrap UPDATE + FTS re-index in a single transaction to prevent
        # data/FTS inconsistency if either operation fails.
        with self.db.transaction():
            self.db.execute(sql, params)
            # Re-index FTS (remove old, insert new)
            self._remove_from_fts(predicate_id)
            self._index_fts(predicate_id)

        return self.get_by_predicate_id(predicate_id)

    # ── Update predicate_id (rename/merge) with manual cascade ─────────────

    _SOURCE_PRIORITY: dict[str, int] = {
        "wikidata": 5,
        "owl": 4,
        "rdfs": 3,
        "rdf": 2,
        "manual": 1,
    }

    def _rename_predicate(
        self, old_id: str, new_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Rename a predicate to a *non‑existing* new_id.

        FTS cleanup runs *before* the transaction (so rowids are still
        resolvable), SQL mutations inside a transaction with deferred FK
        checks, then FTS indexing after.

        Args:
            old_id: Current predicate_id.
            new_id: New predicate_id (guaranteed *not* in the table).
            updates: Prepared field dict (keys = column names).

        Returns:
            Updated predicate dict.
        """
        # Phase 1: FTS cleanup while both rows are addressable
        self._remove_from_fts(old_id)

        # Phase 2: Atomic SQL operations
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

        # Phase 3: FTS index after commit
        self._index_fts(new_id)

        return self.get_by_predicate_id(new_id)

    def _merge_predicate(
        self, old_id: str, new_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge *old* predicate into an *existing* *new* predicate.

        1. Merge labels / descriptions / aliases (data overrides all).
        2. Rewire triples and group-member references (collisions resolved
           by keeping the *new* wins row).
        3. Delete the old predicate row.
        4. Rebuild FTS index for *new*.

        Args:
            old_id: Current predicate_id (will be deleted).
            new_id: Target predicate_id (must already exist in the table).
            data: Additional field updates (etikedoj, priskriboj, etc.).

        Returns:
            Updated predicate dict.
        """
        old = self.get_by_predicate_id(old_id)
        new = self.get_by_predicate_id(new_id)
        # Both guaranteed to exist by caller.

        # ── Merge metadata ──────────────────────────────────────
        old_etikedoj: dict = json.loads(old.get("etikedoj", "{}"))
        new_etikedoj: dict = json.loads(new.get("etikedoj", "{}"))
        data_etikedoj = data.get("etikedoj", {})
        if isinstance(data_etikedoj, str):
            data_etikedoj = json.loads(data_etikedoj)
        merged_etikedoj = {**old_etikedoj, **new_etikedoj, **data_etikedoj}

        old_priskriboj: dict = json.loads(old.get("priskriboj", "{}"))
        new_priskriboj: dict = json.loads(new.get("priskriboj", "{}"))
        merged_priskriboj = {
            **old_priskriboj,
            **new_priskriboj,
            **(
                json.loads(data["priskriboj"])
                if isinstance(data.get("priskriboj"), str)
                else data.get("priskriboj", {})
            ),
        }

        old_aliases: list = json.loads(old.get("aliases", "[]"))
        new_aliases: list = json.loads(new.get("aliases", "[]"))
        if "aliases" in data:
            raw = data["aliases"]
            merged_aliases = json.loads(raw) if isinstance(raw, str) else raw
        else:
            merged_aliases = list(dict.fromkeys(old_aliases + new_aliases))

        old_source_prio = self._SOURCE_PRIORITY.get(old["source"], 0)
        new_source_prio = self._SOURCE_PRIORITY.get(new["source"], 0)
        merged_source = old["source"] if old_source_prio > new_source_prio else new["source"]
        if "source" in data:
            merged_source = data["source"]

        merged_kreita_je = min(old["kreita_je"], new["kreita_je"])
        merged_modifita_je = now()
        merged_label_text = extract_label_text(json.dumps(merged_etikedoj))

        # ── Phase 1: FTS cleanup (both rows still exist) ────────
        self._remove_from_fts(old_id)
        self._remove_from_fts(new_id)

        # ── Phase 2: Atomic SQL operations ──────────────────────
        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            # 1. Update new predicate row with merged data
            conn.execute(
                """UPDATE predicates SET etikedoj = ?, label_text = ?,
                   priskriboj = ?, aliases = ?, source = ?,
                   kreita_je = ?, modifita_je = ?
                   WHERE predicate_id = ?""",
                (
                    json.dumps(merged_etikedoj, ensure_ascii=False),
                    merged_label_text,
                    json.dumps(merged_priskriboj, ensure_ascii=False),
                    json.dumps(merged_aliases, ensure_ascii=False),
                    merged_source,
                    merged_kreita_je,
                    merged_modifita_je,
                    new_id,
                ),
            )

            # 2. Delete old triples that would PK-collide with new triples
            conn.execute(
                """DELETE FROM triples WHERE predicate_id = ?
                   AND (subject_uuid, object_value, object_type) IN (
                       SELECT subject_uuid, object_value, object_type
                       FROM triples WHERE predicate_id = ?
                   )""",
                (old_id, new_id),
            )

            # 3. Update remaining old triples → new_id
            conn.execute(
                "UPDATE triples SET predicate_id = ? WHERE predicate_id = ?",
                (new_id, old_id),
            )

            # 4. Delete old group members that collide with new
            conn.execute(
                """DELETE FROM predicate_group_members WHERE predicate_id = ?
                   AND group_uuid IN (
                       SELECT group_uuid FROM predicate_group_members
                       WHERE predicate_id = ?
                   )""",
                (old_id, new_id),
            )

            # 5. Update remaining old group members → new_id
            conn.execute(
                "UPDATE predicate_group_members SET predicate_id = ? WHERE predicate_id = ?",
                (new_id, old_id),
            )

            # 6. Delete old predicate row
            conn.execute(
                "DELETE FROM predicates WHERE predicate_id = ?",
                (old_id,),
            )

        # Phase 3: FTS index after commit
        self._index_fts(new_id)

        return self.get_by_predicate_id(new_id)

    def update_predicate_id(
        self, old_id: str, new_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Rename/merge a predicate's predicate_id, cascading to all
        references.

        If *new_id* does **not** exist → simple rename (fast path).
        If *new_id* **already** exists → merge: labels are merged
        (new wins on conflict), triples/group-members are re-wired,
        and the old predicate row is deleted.

        Manual SQL in a single transaction handles FK constraints on
        triples and predicate_group_members.  FTS cleanup runs *before*
        the transaction, indexing *after*, to avoid committing the
        transaction prematurely (FTS methods use ``self.db.execute()``
        which auto-commits).

        Args:
            old_id: Current predicate_id.
            new_id: New predicate_id.
            data: Additional field updates (etikedoj, priskriboj, etc.).

        Returns:
            Updated predicate dict.

        Raises:
            ValueError: If *old_id* not found.
        """
        if old_id == new_id:
            return self.update(old_id, data)

        old = self.get_by_predicate_id(old_id)
        if not old:
            raise ValueError(f"Predicate not found: {old_id}")

        existing = self.get_by_predicate_id(new_id)
        if existing:
            return self._merge_predicate(old_id, new_id, data)

        # ── fresh rename ────────────────────────────────────────
        from A_semantika._id_rename_helpers import (
            check_predicate_group_member_collision,
            check_triple_predicate_collision,
        )
        check_triple_predicate_collision(self.db, old_id, new_id)
        check_predicate_group_member_collision(self.db, old_id, new_id)

        updates: dict[str, Any] = {}
        updates["predicate_id"] = new_id
        updates["modifita_je"] = now()

        if "etikedoj" in data:
            etikedoj_val = data["etikedoj"]
            if isinstance(etikedoj_val, dict):
                etikedoj_val = json.dumps(etikedoj_val)
            updates["etikedoj"] = etikedoj_val
            updates["label_text"] = extract_label_text(etikedoj_val)
        if "priskriboj" in data:
            updates["priskriboj"] = _ensure_json(data["priskriboj"])
        if "aliases" in data:
            updates["aliases"] = _ensure_json(data["aliases"])
        if "source" in data:
            updates["source"] = data["source"]
        # Pass through any other fields the caller may have set
        for k, v in data.items():
            if k not in ("etikedoj", "priskriboj", "aliases", "source"):
                updates[k] = v

        return self._rename_predicate(old_id, new_id, updates)

    # ── Trash support ───────────────────────────────────────────────────

    def count_referencing_triples(self, predicate_id: str) -> int:
        """Return the number of triples referencing this predicate."""
        row = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM triples WHERE predicate_id = ?",
            (predicate_id,),
        )
        return row["cnt"] if row else 0

    def delete(self, predicate_id: str, soft: bool = True) -> None:
        """Delete a predicate.

        Raises ``ValueError`` if triples still reference the predicate
        (use ``--forte`` on the CLI to cascade-delete them).

        If soft=True, moves to trash (predicates_rubujo) instead of
        permanent deletion. Restorable via restore().
        """
        ref_count = self.count_referencing_triples(predicate_id)
        if ref_count > 0:
            raise ValueError(
                f"Cannot delete predicate '{predicate_id}': {ref_count} triple(s) "
                f"still reference it."
            )
        if soft:
            self._move_to_trash(predicate_id)
        else:
            self._remove_from_fts(predicate_id)
            self.db.execute(
                "DELETE FROM predicates WHERE predicate_id = ?",
                (predicate_id,),
            )

    def _move_to_trash(self, predicate_id: str) -> None:
        """Move predicate to trash table using predicate_id column.

        Raises ``ValueError`` if triples still reference the predicate.
        """
        ref_count = self.count_referencing_triples(predicate_id)
        if ref_count > 0:
            raise ValueError(
                f"Cannot delete predicate '{predicate_id}': {ref_count} triple(s) "
                f"still reference it."
            )
        entry = self.db.execute_one(
            f"SELECT * FROM {self.table} WHERE predicate_id = ?", (predicate_id,)
        )
        if not entry:
            return

        # Always remove from FTS — predicates_fts is managed manually.
        self._remove_from_fts(predicate_id)

        entry["forigita_je"] = datetime.now(timezone.utc).isoformat()
        entry.setdefault("modifita_je", entry["forigita_je"])

        columns = list(entry.keys())
        values = list(entry.values())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT OR REPLACE INTO {self._trash_table} ({', '.join(columns)}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(sql, values)
            conn.execute(f"DELETE FROM {self.table} WHERE predicate_id = ?", (predicate_id,))

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

        # Always re-index FTS — predicates_fts is managed manually.
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
        """
        safe_tokens = []
        for word in query.strip().split():
            cleaned = "".join(c for c in word if c.isalnum() or c == "_")
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

        # Try FTS5 first
        self._ensure_fts()
        fts_query = self._sanitize_fts_query(query)
        if fts_query:
            fts_sql = """
                SELECT p.* FROM predicates p
                JOIN predicates_fts f ON p.rowid = f.rowid
                WHERE predicates_fts MATCH ?
                LIMIT ?
            """
            results = self.db.execute(fts_sql, (fts_query, limit))
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
