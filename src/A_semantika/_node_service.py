"""NodeService — CRUDService subclass for knowledge graph nodes.

Supports FTS5 search on label_text + difin_text.
Auto-denormalizes etikedoj/difinoj JSON into flat text fields.
UUID override on create for manual assignment.
"""
from __future__ import annotations

import json
import sqlite3
import uuid as _uuid
from typing import Any

from A import warning as _warning
from A.core.service import CRUDService
from A.data.search import FTSConfig
from A_semantika._node_helpers import FTS5_KEYWORDS, extract_difin_text, extract_label_text
from A_semantika.data.storage import now


class AmbiguousUUIDError(ValueError):
    """Raised when a UUID prefix matches multiple nodes."""
    pass


def _fts_config() -> FTSConfig:
    """FTS config for nodes: search across label and definition text."""
    return FTSConfig(
        table="nodes",
        fts_columns=["label_text", "difin_text"],
    )


class NodeService(CRUDService):
    """Service for managing knowledge graph nodes.

    Features:
    - FTS5 full-text search on label_text + difin_text
    - Auto-denormalization of etikedoj/difinoj JSON into flat text
    - Human-readable node_id (not UUID) as primary key
    - Optional auto-generated UUID if node_id not provided
    - Undo/trash enabled (default undo_size=10)
    """

    def __init__(self, db: Any) -> None:
        super().__init__(
            db=db,
            table="nodes",
            fts_config=_fts_config(),
            undo_size=10,
        )

    # ── Override create to support optional node_id ──────────────────────
    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a node with optional pre-assigned node_id."""
        node_id_val = data.get("node_id") or str(_uuid.uuid4())
        timestamp = now()

        raw = {
            "node_id": node_id_val,
            "etikedoj": json.dumps(data.get("etikedoj", {})),
            "label_text": extract_label_text(data.get("etikedoj", {})),
            "difinoj": json.dumps(data.get("difinoj", {})),
            "difin_text": extract_difin_text(data.get("difinoj", {})),
            "kreita_je": timestamp,
            "modifita_je": timestamp,
        }
        # Insert directly to bypass CRUDService's auto-UUID generation
        try:
            self.db.execute(
                "INSERT INTO nodes (node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
                "VALUES (:node_id, :etikedoj, :label_text, :difinoj, :difin_text, :kreita_je, :modifita_je)",
                raw,
            )
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"Node with ID '{node_id_val}' already exists. "
                f"Use 'A semantika nodo modifi {node_id_val}' to modify it."
            ) from e
        # Re-index FTS for the denormalized values
        if self._fts_config:
            self._index_fts(node_id_val)

        # Track for undo
        if self._undo_manager is not None:
            from A.core.service import create_undo_operation

            op = create_undo_operation(
                operation_type="add",
                table=self.table,
                record_uuid=node_id_val,
                new_data=raw,
            )
            self._undo_manager.push(op)

        return self.get(node_id_val)

    # ── Override get to use node_id column ───────────────────────────────

    def get(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by exact node_id.

        Uses exact match (not LIKE prefix matching) to avoid silent
        ambiguity.  For prefix resolution, use
        :meth:`resolve_uuid_prefix` which detects ambiguous matches.
        """
        return self.db.execute_one(
            f"SELECT * FROM {self.table} WHERE node_id = ? COLLATE NOCASE", (node_id,)
        )

    # ── Override update to use node_id column ────────────────────────────

    def update(self, node_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a node, re-denormalizing labels if etikedoj/difinoj changed."""
        old = self.get(node_id)
        if not old:
            msg = f"Node not found: {node_id}"
            raise ValueError(msg)

        updates = dict(data)
        now_ts = now()

        # Recompute denormalized fields if labels or definitions changed
        if "etikedoj" in updates:
            etikedoj = updates["etikedoj"]
            if isinstance(etikedoj, dict):
                etikedoj = json.dumps(etikedoj)
            updates["etikedoj"] = etikedoj
            updates["label_text"] = extract_label_text(etikedoj)

        if "difinoj" in updates:
            difinoj = updates["difinoj"]
            if isinstance(difinoj, dict):
                difinoj = json.dumps(difinoj)
            updates["difinoj"] = difinoj
            updates["difin_text"] = extract_difin_text(difinoj)

        updates["modifita_je"] = now_ts

        # Build SET clause dynamically
        set_parts = []
        params = []
        for key, val in updates.items():
            set_parts.append(f"{key} = ?")
            params.append(val)
        params.append(node_id)

        sql = f"UPDATE nodes SET {', '.join(set_parts)} WHERE node_id = ?"
        self.db.execute(sql, params)

        # Re-index FTS (wrapped in transaction so partial failure doesn't orphan FTS entries)
        if self._fts_config:
            with self.db.transaction():
                self._remove_from_fts(node_id)
                self._index_fts(node_id)

        # Track for undo
        if self._undo_manager is not None and old:
            from A.core.service import create_undo_operation

            op = create_undo_operation(
                operation_type="modify",
                table=self.table,
                record_uuid=node_id,
                old_data=old,
                new_data=updates,
            )
            self._undo_manager.push(op)

        return self.get(node_id)

    # ── Override delete to use node_id column ────────────────────────────

    def delete(self, node_id: str, soft: bool = True) -> None:
        """Delete a node.

        Args:
            node_id: Node ID
            soft: If True, move to trash table. If False, permanent delete.
        """
        old_data = self.get(node_id)

        if soft:
            self._move_to_trash(node_id)
        else:
            if self._fts_config:
                self._remove_from_fts(node_id)
            sql = f"DELETE FROM {self.table} WHERE node_id = ?"
            with self.db.transaction() as conn:
                conn.execute(sql, (node_id,))

        if self._undo_manager is not None and old_data:
            from A.core.service import create_undo_operation

            self._undo_manager.push(create_undo_operation(
                operation_type="delete",
                table=self.table,
                record_uuid=node_id,
                old_data=old_data,
            ))

        try:
            self._post_delete(node_id, old_data, soft)
        except Exception:
            _warning(f"Post-delete cleanup failed for node: {node_id}")

    # ── Override _move_to_trash to use node_id column ────────────────────

    def _move_to_trash(self, node_id: str) -> None:
        """Move node to trash table."""
        entry = self.db.execute_one(
            f"SELECT * FROM {self.table} WHERE node_id = ?", (node_id,)
        )
        if not entry:
            return

        if self._fts_config:
            self._remove_from_fts(node_id)

        from datetime import datetime, timezone

        entry["forigita_je"] = datetime.now(timezone.utc).isoformat()
        entry.setdefault("modifita_je", entry["forigita_je"])

        columns = list(entry.keys())
        values = list(entry.values())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT OR REPLACE INTO {self._trash_table} ({', '.join(columns)}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(sql, values)
            conn.execute(f"DELETE FROM {self.table} WHERE node_id = ?", (node_id,))

    # ── Override restore to use node_id column ───────────────────────────

    def restore(self, node_id: str) -> dict[str, Any] | None:
        """Restore node from trash."""
        entry = self.db.execute_one(
            f"SELECT * FROM {self._trash_table} WHERE node_id = ?", (node_id,)
        )
        if not entry:
            return None

        from datetime import datetime, timezone

        entry["modifita_je"] = datetime.now(timezone.utc).isoformat()
        entry.pop("forigita_je", None)

        columns = list(entry.keys())
        values = list(entry.values())
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(insert_sql, values)
            conn.execute(f"DELETE FROM {self._trash_table} WHERE node_id = ?", (node_id,))

        # Re-index FTS for the restored node
        if self._fts_config:
            self._index_fts(node_id)

        return entry


    # ── Override permanent_delete to use node_id column ────────────────────

    def permanent_delete(self, node_id: str) -> bool:
        """Permanently delete a single entry from trash using node_id.

        Overrides CRUDService.permanent_delete which uses 'uuid' column.
        """
        sql = f"DELETE FROM {self._trash_table} WHERE node_id = ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, (node_id,))
            return cursor.rowcount > 0


    # ── Override empty_trash to use correct ISO timestamp comparison ──────

    def get_trash_older_than(self, days: int, limit: int = 99999) -> list[dict]:
        """Get trash items older than N days, filtering in SQL.

        Avoids loading all trash items into memory when only a subset
        is needed (e.g., for preview before ``malplenigi --days``).
        """
        from datetime import datetime, timezone, timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return self.db.execute(
            f"SELECT * FROM {self._trash_table} WHERE forigita_je < ? ORDER BY node_id LIMIT ?",
            (cutoff, limit),
        )

    def empty_trash(self, days: int = 30) -> int:
        """Permanently delete entries from trash older than days.

        Overrides CRUDService.empty_trash which uses SQLite datetime()
        function that mangles ISO timestamps with 'T' separators.
        """
        from datetime import datetime, timezone, timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        sql = f"DELETE FROM {self._trash_table} WHERE forigita_je < ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql, (cutoff,))
            return cursor.rowcount

    def empty_all_trash(self) -> int:
        """Permanently delete ALL entries from the trash table.

        Unlike ``empty_trash()`` which filters by age, this deletes
        everything regardless of when it was deleted.  Used by
        ``rubujo malplenigi`` without ``--days``.
        """
        sql = f"DELETE FROM {self._trash_table}"
        with self.db.transaction() as conn:
            cursor = conn.execute(sql)
            return cursor.rowcount

    # ── Override _ensure_fts — use node_id instead of uuid in FTS schema ──

    def _ensure_fts(self) -> None:
        """Create FTS5 virtual table with node_id column (not uuid)."""
        if not self._fts_config:
            return
        config = self._fts_config
        columns_def = ", ".join(config.fts_columns)
        self.db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {config.fts_table}"
            f" USING fts5("
            f"  node_id UNINDEXED,"
            f"  {columns_def},"
            f"  content={config.table},"
            f"  content_rowid=rowid,"
            f"  tokenize='{config.tokenize}'"
            f")"
        )

        # Populate FTS if empty
        count = self.db.execute_one(
            f"SELECT COUNT(*) AS cnt FROM {config.fts_table}"
        )
        if count and count["cnt"] == 0:
            self.db.execute(
                f"INSERT INTO {config.fts_table}({config.fts_table}) VALUES('rebuild')"
            )

    # ── Override _remove_from_fts for SQLite 3.50+ compatibility ────────

    def _remove_from_fts(self, node_id: str) -> None:
        """Remove node from FTS index using FTS5 'delete' command.

        Overrides CRUDService._remove_from_fts which uses a direct
        ``DELETE FROM fts_table`` — this causes ``database disk image is
        malformed`` on SQLite ≥ 3.50 when the FTS table uses external
        content (content = nodes).  The FTS5 ``'delete'`` command avoids
        this bug.
        """
        if not self._fts_config:
            return
        row = self.db.execute_one(
            f"SELECT rowid FROM {self.table} WHERE node_id = ?", (node_id,)
        )
        if not row or row.get("rowid") is None:
            return
        self.db.execute(
            f"INSERT INTO {self._fts_config.fts_table}({self._fts_config.fts_table}, rowid)"
            " VALUES('delete', ?)",
            (row["rowid"],),
        )

    # ── Override _index_fts to use node_id column ─────────────────────────

    def _index_fts(self, node_id: str) -> None:
        """Index a single node in FTS5.

        Override to use node_id instead of uuid column.
        Self-contained — avoids A-core build_index_sql which hardcodes uuid.
        """
        if not self._fts_config:
            return
        entry = self.db.execute_one(
            f"SELECT rowid, node_id, "
            f"{', '.join(self._fts_config.fts_columns)} "
            f"FROM {self.table} WHERE node_id = ?",
            (node_id,)
        )
        if not entry:
            return

        # Build INSERT with node_id instead of uuid
        values = [entry["rowid"], node_id]
        for col in self._fts_config.fts_columns:
            val = entry.get(col, "")
            if col in self._fts_config.normalize:
                val = self._fts_config.normalize[col](val)
            values.append(val)

        placeholders = ", ".join(["?"] * (len(self._fts_config.fts_columns) + 2))
        fts_cols = ", ".join(["node_id"] + self._fts_config.fts_columns)
        sql = (
            f"INSERT INTO {self._fts_config.fts_table} (rowid, {fts_cols})"
            f" VALUES ({placeholders})"
        )
        self.db.execute(sql, values)

    # ── node_id prefix resolution ────────────────────────────────────────

    def resolve_uuid_prefix(self, prefix: str) -> dict | None:
        """Resolve a node_id prefix to a full node.

        Returns the node dict if exactly one match, None if no match.
        Raises AmbiguousUUIDError if prefix is ambiguous (multiple matches).
        Searches are case-insensitive (COLLATE NOCASE).
        """
        if not prefix:
            return None

        # Full node_id match via exact match (case-insensitive)
        node = self.db.execute_one(
            "SELECT * FROM nodes WHERE node_id = ? COLLATE NOCASE", (prefix,)
        )
        if node:
            return node

        # Prefix search via LIKE (case-insensitive, with wildcard escaping)
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matches = self.db.execute(
            "SELECT * FROM nodes WHERE node_id LIKE ? COLLATE NOCASE ESCAPE '\\'",
            (f"{escaped}%",),
        )
        if not matches:
            return None
        if len(matches) > 1:
            msg = f"Node ID prefix '{prefix}' is ambiguous ({len(matches)} matches)"
            raise AmbiguousUUIDError(msg)
        return matches[0]

    def get_display_label(self, node_id_or_prefix: str) -> tuple[str, str]:
        """Get (display_label, language_code) for a node.

        Returns label in eo, falling back to en, then to the first available,
        then to the node_id prefix as last resort.
        """
        node = self.resolve_uuid_prefix(node_id_or_prefix)
        if not node:
            return (node_id_or_prefix, "")

        try:
            labels = json.loads(node["etikedoj"])
        except (json.JSONDecodeError, TypeError):
            return (node["node_id"][:8], "")

        if not isinstance(labels, dict):
            return (node["node_id"][:8], "")

        for lang in ("eo", "en"):
            val = labels.get(lang)
            if val and isinstance(val, str):
                return (val, lang)

        # First non-empty
        for val in labels.values():
            if val and isinstance(val, str):
                return (val, "")
        return (node["node_id"][:8], "")

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search on nodes via FTS5.

        Falls back to LIKE on label_text if FTS returns nothing.
        """
        if not query or not query.strip():
            return self.list(limit=limit)

        # Try FTS first
        # Sanitize FTS5 query: strip special characters that can crash MATCH,
        # but treat FTS5 keywords (AND, OR, NOT, NEAR, COLUMN) as regular
        # content terms by lowercasing them instead of stripping them out.
        safe_tokens = []
        for word in query.strip().split():
            cleaned = "".join(c for c in word if c.isalnum() or c in ("_", "."))
            if not cleaned:
                continue
            if cleaned.upper() in FTS5_KEYWORDS:
                cleaned = cleaned.lower()
            safe_tokens.append(f"{cleaned}*")
        if not safe_tokens:
            return self.list(limit=limit)
        fts_query = " OR ".join(safe_tokens)
        fts_sql = """
            SELECT n.* FROM nodes n
            JOIN nodes_fts f ON n.node_id = f.node_id
            WHERE nodes_fts MATCH ?
            LIMIT ?
        """
        results = self.db.execute(fts_sql, (fts_query, limit))
        if results:
            return results

        # Fallback: LIKE on label_text (case-insensitive)
        like_sql = "SELECT * FROM nodes WHERE label_text LIKE ? COLLATE NOCASE LIMIT ?"
        pattern = f"%{query}%"
        return self.db.execute(like_sql, (pattern, limit))
