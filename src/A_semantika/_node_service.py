"""NodeService — CRUDService subclass for knowledge graph nodes.

Supports FTS5 search on label_text + difin_text.
Auto-denormalizes etikedoj/difinoj JSON into flat text fields.
UUID override on create for manual assignment.
"""
from __future__ import annotations

import json
import uuid as _uuid
from typing import Any

from A.core.service import CRUDService
from A.data.search import FTSConfig
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


def _extract_label_text(etikedoj: str | dict) -> str:
    """Denormalize etikedoj JSON into a flat searchable string.

    Concatenates all label values separated by spaces.
    """
    try:
        labels = json.loads(etikedoj) if isinstance(etikedoj, str) else etikedoj
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(labels, dict):
        return ""
    return " ".join(str(v) for v in labels.values() if v)


def _extract_difin_text(difinoj: str | dict) -> str:
    """Denormalize difinoj JSON into a flat searchable string."""
    try:
        defns = json.loads(difinoj) if isinstance(difinoj, str) else difinoj
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(defns, dict):
        return ""
    return " ".join(str(v) for v in defns.values() if v)


class NodeService(CRUDService):
    """Service for managing knowledge graph nodes.

    Features:
    - FTS5 full-text search on label_text + difin_text
    - Auto-denormalization of etikedoj/difinoj JSON into flat text
    - Optional UUID override on create
    - Undo/trash enabled (default undo_size=10)
    """

    def __init__(self, db: Any) -> None:
        super().__init__(
            db=db,
            table="nodes",
            fts_config=_fts_config(),
            undo_size=10,
        )

    # ── Override create to support optional UUID ────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a node, with optional pre-assigned UUID.

        If data contains a 'uuid' key, use it instead of generating one.
        """
        node_uuid = data.pop("uuid", None) or str(_uuid.uuid4())
        timestamp = now()

        raw = {
            "uuid": node_uuid,
            "etikedoj": json.dumps(data.get("etikedoj", {})),
            "label_text": _extract_label_text(data.get("etikedoj", {})),
            "difinoj": json.dumps(data.get("difinoj", {})),
            "difin_text": _extract_difin_text(data.get("difinoj", {})),
            "kreita_je": timestamp,
            "modifita_je": timestamp,
        }
        # Insert directly to bypass CRUDService's auto-UUID generation
        self.db.execute(
            "INSERT INTO nodes (uuid, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES (:uuid, :etikedoj, :label_text, :difinoj, :difin_text, :kreita_je, :modifita_je)",
            raw,
        )
        # Re-index FTS for the denormalized values
        if self._fts_config:
            self._index_fts(node_uuid)

        # Track for undo
        if self._undo_manager is not None:
            from A.core.service import create_undo_operation

            op = create_undo_operation(
                operation_type="add",
                table=self.table,
                record_uuid=node_uuid,
                new_data=raw,
            )
            self._undo_manager.push(op)

        return self.get(node_uuid)

    # ── Override update to re-index FTS after denormalization ───────────

    def update(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a node, re-denormalizing labels if etikedoj/difinoj changed."""
        old = self.get(uuid)
        if not old:
            msg = f"Node not found: {uuid}"
            raise ValueError(msg)

        updates = dict(data)
        now_ts = now()

        # Recompute denormalized fields if labels or definitions changed
        if "etikedoj" in updates:
            etikedoj = updates["etikedoj"]
            if isinstance(etikedoj, dict):
                etikedoj = json.dumps(etikedoj)
            updates["etikedoj"] = etikedoj
            updates["label_text"] = _extract_label_text(etikedoj)

        if "difinoj" in updates:
            difinoj = updates["difinoj"]
            if isinstance(difinoj, dict):
                difinoj = json.dumps(difinoj)
            updates["difinoj"] = difinoj
            updates["difin_text"] = _extract_difin_text(difinoj)

        updates["modifita_je"] = now_ts

        # Build SET clause dynamically
        set_parts = []
        params = []
        for key, val in updates.items():
            set_parts.append(f"{key} = ?")
            params.append(val)
        params.append(uuid)

        sql = f"UPDATE nodes SET {', '.join(set_parts)} WHERE uuid = ?"
        self.db.execute(sql, params)

        # Re-index FTS
        if self._fts_config:
            self._remove_from_fts(uuid)
            self._index_fts(uuid)

        # Track for undo
        if self._undo_manager is not None and old:
            from A.core.service import create_undo_operation

            op = create_undo_operation(
                operation_type="modify",
                table=self.table,
                record_uuid=uuid,
                old_data=old,
                new_data=updates,
            )
            self._undo_manager.push(op)

        return self.get(uuid)

    # ── Override _remove_from_fts for SQLite 3.50+ compatibility ────────

    def _remove_from_fts(self, uuid: str) -> None:
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
            f"SELECT rowid FROM {self.table} WHERE uuid = ?", (uuid,)
        )
        if not row or row.get("rowid") is None:
            return
        self.db.execute(
            f"INSERT INTO {self._fts_config.fts_table}({self._fts_config.fts_table}, rowid)"
            " VALUES('delete', ?)",
            (row["rowid"],),
        )

    # ── UUID prefix resolution ──────────────────────────────────────────

    def resolve_uuid_prefix(self, prefix: str) -> dict | None:
         """Resolve a UUID prefix to a full node.

         Returns the node dict if exactly one match, None if no match.
         Raises AmbiguousUUIDError if prefix is ambiguous (multiple matches).
         """
         if not prefix:
             return None

         # If prefix looks like a full UUID (36 chars with dashes), try exact match
         if len(prefix) == 36 and prefix.count("-") == 4:
             node = self.db.execute_one("SELECT * FROM nodes WHERE uuid = ?", (prefix,))
             if node:
                 return node

         # Prefix search via LIKE
         matches = self.db.execute(
             "SELECT * FROM nodes WHERE uuid LIKE ?",
             (f"{prefix}%",),
         )
         if not matches:
             return None
         if len(matches) > 1:
             msg = f"UUID prefix '{prefix}' is ambiguous ({len(matches)} matches)"
             raise AmbiguousUUIDError(msg)
         return matches[0]

    def get_display_label(self, uuid_or_prefix: str) -> tuple[str, str]:
        """Get (display_label, language_code) for a node.

        Returns label in eo, falling back to en, then to the first available,
        then to the UUID prefix as last resort.
        """
        node = self.resolve_uuid_prefix(uuid_or_prefix)
        if not node:
            return (uuid_or_prefix, "")

        try:
            labels = json.loads(node["etikedoj"])
        except (json.JSONDecodeError, TypeError):
            return (node["uuid"][:8], "")

        if not isinstance(labels, dict):
            return (node["uuid"][:8], "")

        for lang in ("eo", "en"):
            val = labels.get(lang)
            if val and isinstance(val, str):
                return (val, lang)

        # First non-empty
        for val in labels.values():
            if val and isinstance(val, str):
                return (val, "")
        return (node["uuid"][:8], "")

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Full-text search on nodes via FTS5.

        Falls back to LIKE on label_text if FTS returns nothing.
        """
        if not query or not query.strip():
            return self.list(limit=limit)

        # Try FTS first
        # Sanitize FTS5 query: strip special characters that can crash MATCH
        # FTS5 special chars: " * ^ - + ~ ( ) { } [ ] : < > %
        # FTS5 reserved keywords: AND, OR, NOT, NEAR, COLUMN
        # Hyphens are removed entirely (FTS5 treats "-" as a NOT operator)
        _FTS5_KEYWORDS = {"AND", "OR", "NOT", "NEAR", "COLUMN"}
        safe_tokens = []
        for word in query.strip().split():
            # Remove all FTS5 special characters including hyphens
            cleaned = "".join(c for c in word if c.isalnum() or c in ("_", "."))
            if not cleaned:
                continue
            # Skip FTS5 reserved keywords (they'd cause syntax errors as prefix terms)
            if cleaned.upper() in _FTS5_KEYWORDS:
                continue
            safe_tokens.append(f"{cleaned}*")
        if not safe_tokens:
            return self.list(limit=limit)
        fts_query = " OR ".join(safe_tokens)
        fts_sql = """
            SELECT n.* FROM nodes n
            JOIN nodes_fts f ON n.uuid = f.uuid
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
