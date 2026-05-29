"""CRUDService for knowledge graph nodes — FTS5, label denorm, node_id PK."""
from __future__ import annotations

import json
import sqlite3
import uuid as _uuid
from typing import Any

from A import warning as _warning
from A.core.service import CRUDService
from A_semantika._node_helpers import (
    AmbiguousUUIDError,
    extract_difin_text,
    extract_label_text,
    get_display_label,
)
from A_semantika._node_search import NodeSearchMixin, _fts_config
from A_semantika.data.storage import now


class NodeService(NodeSearchMixin, CRUDService):
    """Service for managing knowledge graph nodes (FTS5, label denorm, node_id PK)."""

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
        # Insert directly to bypass CRUDService's auto-UUID generation.
        # Wrap INSERT + FTS index in a transaction for consistency with
        # update() and the base CRUDService.create() pattern.
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO nodes (node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
                    "VALUES (:node_id, :etikedoj, :label_text, :difinoj, :difin_text, :kreita_je, :modifita_je)",
                    raw,
                )
                # Re-index FTS for the denormalized values inside the same transaction
                if self._fts_config:
                    self._index_fts(node_id_val)
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"Node with ID '{node_id_val}' already exists. "
                f"Use 'A semantika nodo modifi {node_id_val}' to modify it."
            ) from e

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
        """Get a node by exact node_id (case-insensitive).

        Uses COLLATE NOCASE for case-insensitive matching, consistent with
        :meth:`resolve_node_id_prefix` and all other node lookups. Case
        collisions (e.g. ``ABC`` vs ``abc``) are prevented by SQLite TEXT
        PRIMARY KEY which is case-sensitive, so the NOCASE query will match
        the single existing variant. For prefix resolution, use
        :meth:`resolve_node_id_prefix`.
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

        # Wrap UPDATE + FTS re-index in a single transaction to prevent
        # data/FTS inconsistency if either operation fails.
        if self._fts_config:
            with self.db.transaction() as conn:
                conn.execute(sql, params)
                self._remove_from_fts(node_id)
                self._index_fts(node_id)
        else:
            self.db.execute(sql, params)

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

    # ── Update node_id (rename) with manual cascade ───────────────────────

    def update_node_id(
        self, old_id: str, new_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Rename a node's node_id, cascading to all referencing triples.

        This performs manual SQL UPDATEs in a single transaction to
        bypass the ``object_node_uuid`` generated FK column limitation
        (SQLite cannot cascade through generated columns).

        Args:
            old_id: Current node_id.
            new_id: New node_id.
            data: Additional field updates (etikedoj, difinoj, etc.).

        Returns:
            Updated node dict.

        Raises:
            ValueError: If old_id not found, new_id already exists, or
                PK collision would occur on triples.
        """
        # Pre-checks (before transaction)
        old = self.get(old_id)
        if not old:
            raise ValueError(f"Node not found: {old_id}")

        existing = self.db.execute_one(
            "SELECT node_id FROM nodes WHERE node_id = ?", (new_id,)
        )
        if existing:
            raise ValueError(
                f"New node ID '{new_id}' already exists"
            )

        from A_semantika._id_rename_helpers import (
            check_triple_object_collision,
            check_triple_subject_collision,
        )
        check_triple_subject_collision(self.db, old_id, new_id)
        check_triple_object_collision(self.db, old_id, new_id)

        # Build updates like update() does
        updates = dict(data)
        now_ts = now()
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

        updates["node_id"] = new_id
        updates["modifita_je"] = now_ts

        # Manual cascade in a single transaction.
        # Defer FK checks until COMMIT: the PK change (step 1) temporarily
        # orphans referencing triples, which are re-parented in steps 2-3.
        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")
            # 1. Update the node's PK + fields
            set_parts = []
            params = []
            for key, val in updates.items():
                set_parts.append(f"{key} = ?")
                params.append(val)
            params.append(old_id)
            conn.execute(
                f"UPDATE nodes SET {', '.join(set_parts)} WHERE node_id = ?",
                params,
            )

            # 2. Update triple subject references
            conn.execute(
                "UPDATE triples SET subject_uuid = ? WHERE subject_uuid = ?",
                (new_id, old_id),
            )

            # 3. Update triple object references (URI nodes only)
            conn.execute(
                "UPDATE triples SET object_value = ? "
                "WHERE object_type = 'uri' AND object_value = ?",
                (new_id, old_id),
            )
            # object_node_uuid auto-recomputes from object_value (generated column)

            # 4. Re-index FTS
            if self._fts_config:
                self._remove_from_fts(old_id)
                self._index_fts(new_id)

        # No undo tracking for ID renames (v1 limitation)
        return self.get(new_id)

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
            # Save rowid **before** deletion so we can remove the FTS
            # entry after the node is gone.
            saved_rowid: int | None = None
            if self._fts_config:
                row = self.db.execute_one(
                    f"SELECT rowid FROM {self.table} WHERE node_id = ?",
                    (node_id,),
                )
                saved_rowid = row["rowid"] if row else None
            sql = f"DELETE FROM {self.table} WHERE node_id = ?"
            with self.db.transaction() as conn:
                conn.execute(sql, (node_id,))
            if saved_rowid is not None:
                self._remove_fts_by_rowid(node_id, saved_rowid)

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
        except (sqlite3.Error, OSError) as _exc:
            _warning(f"Post-delete cleanup failed for node: {node_id}: {_exc}")

    # ── Override _move_to_trash to use node_id column ────────────────────

    def _move_to_trash(self, node_id: str) -> None:
        """Move node to trash table."""
        entry = self.db.execute_one(
            f"SELECT * FROM {self.table} WHERE node_id = ?", (node_id,)
        )
        if not entry:
            return

        from datetime import datetime, timezone

        entry["forigita_je"] = datetime.now(timezone.utc).isoformat()
        entry.setdefault("modifita_je", entry["forigita_je"])

        columns = list(entry.keys())
        values = list(entry.values())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT OR REPLACE INTO {self._trash_table} ({', '.join(columns)}) VALUES ({placeholders})"

        # Save the rowid **before** deletion so we can remove the FTS
        # entry after the node is gone.  Removing FTS after deletion
        # ensures that if the 'delete' command fails and falls back to
        # a rebuild, the node is already absent from the content table
        # and won't be re-indexed.
        saved_rowid: int | None = None
        if self._fts_config:
            row = self.db.execute_one(
                f"SELECT rowid FROM {self.table} WHERE node_id = ?", (node_id,)
            )
            saved_rowid = row["rowid"] if row else None

        with self.db.transaction() as conn:
            conn.execute(sql, values)
            conn.execute(f"DELETE FROM {self.table} WHERE node_id = ?", (node_id,))

        # Remove from FTS AFTER the node is deleted from the content
        # table.  If the 'delete' command raises DatabaseError, a
        # warning is logged (no rebuild — the stale FTS entry is
        # benign; the next search() will rebuild on demand).
        if saved_rowid is not None:
            self._remove_fts_by_rowid(node_id, saved_rowid)

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


