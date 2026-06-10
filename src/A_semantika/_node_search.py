"""Mixin for NodeService — search, ID resolution, FTS management.

Extracted from _node_service.py to keep that file under 500 lines.
Contains search, node_id prefix resolution, and FTS index operations.
"""

from __future__ import annotations

import logging
import sqlite3
import warnings
from typing import Any

logger = logging.getLogger(__name__)
from A_semantika._node_helpers import AmbiguousUUIDError, FTS5_KEYWORDS, sanitize_node_id


def _fts_config() -> Any:
    """FTS config for nodes: search across label and definition text."""
    from A.data.search import FTSConfig

    return FTSConfig(
        table="nodes",
        fts_columns=["label_text", "difin_text"],
    )


class NodeSearchMixin:
    """Mixin providing search, node_id prefix resolution, and FTS index management.

    Intended to be used as a mixin with ``CRUDService``-based classes
    (e.g. ``class NodeService(NodeSearchMixin, CRUDService)``).
    Expects ``self.db``, ``self._fts_config``, and ``self.table``
    to be set by the concrete class.
    """

    # ── node_id prefix resolution ──────────────────────────────────────────

    def resolve_node_id_prefix(self, prefix: str) -> dict | None:
        """Resolve a node_id prefix to a full node.

        Returns the node dict if exactly one match, None if no match.
        Raises AmbiguousUUIDError if prefix is ambiguous (multiple matches).
        Searches are case-insensitive (COLLATE NOCASE).
        """
        if not prefix:
            return None

        # Strip invisible Unicode characters from input so that
        # contaminated node_ids (e.g. with U+200B zero-width spaces
        # from copy-paste) are still discoverable.
        prefix = sanitize_node_id(prefix)

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
            raise AmbiguousUUIDError(msg, matches=matches)
        return matches[0]

    def resolve_node_id_substring(self, text: str) -> dict | None:
        """Resolve a node by searching for ``text`` as a substring of node_id.

        This is a broader (slower) match than :meth:`resolve_node_id_prefix`
        — it uses ``LIKE '%text%'`` instead of ``LIKE 'text%'``.  Use it
        when the user may have entered only part of a node_id that does
        *not* start at the beginning (e.g. ``MILITO`` for ``GAULA_MILITO``).

        Returns the node dict if exactly one match, ``None`` if no match.
        Raises ``AmbiguousUUIDError`` if multiple nodes match.
        """
        if not text:
            return None
        text = sanitize_node_id(text)
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matches = self.db.execute(
            "SELECT * FROM nodes WHERE node_id LIKE ? COLLATE NOCASE ESCAPE '\\'",
            (f"%{escaped}%",),
        )
        if not matches:
            return None
        if len(matches) > 1:
            msg = f"Node ID '{text}' is ambiguous ({len(matches)} matches)"
            raise AmbiguousUUIDError(msg, matches=matches)
        return matches[0]

    # ── Backward-compat alias: resolve_uuid_prefix -> resolve_node_id_prefix ──

    def resolve_uuid_prefix(self, prefix: str) -> dict | None:
        """Deprecated: use :meth:`resolve_node_id_prefix` instead."""
        warnings.warn(
            "resolve_uuid_prefix() is deprecated, use resolve_node_id_prefix()",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.resolve_node_id_prefix(prefix)

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
            cleaned = "".join(c for c in word if c.isalnum() or c == "_")
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
        try:
            results = self.db.execute(fts_sql, (fts_query, limit))
        except sqlite3.DatabaseError:
            # FTS index has dangling references (e.g. rows that were
            # deleted without a matching 'delete' command). Rebuild from
            # current content table and retry.
            logger.warning("FTS index inconsistent — rebuilding and retrying search.")
            self.db.execute(
                f"INSERT INTO {self._fts_config.fts_table}"
                f"({self._fts_config.fts_table}) VALUES('rebuild')"
            )
            results = self.db.execute(fts_sql, (fts_query, limit))
        if results:
            return results

        # Fallback: LIKE on label_text (case-insensitive)
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_sql = "SELECT * FROM nodes WHERE label_text LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT ?"
        pattern = f"%{escaped}%"
        return self.db.execute(like_sql, (pattern, limit))

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

    # ── Override _remove_from_fts (FTS5 'delete' command) ────────────────

    def _remove_from_fts(self, node_id: str) -> None:
        """Remove node from FTS index using FTS5 'delete' command.

        Uses the FTS5 ``'delete'`` command (rowid-only form) rather than
        a direct ``DELETE FROM fts_table`` because the latter causes
        ``database disk image is malformed`` on SQLite with external
        content tables.

        .. caution::

           The caller **must** ensure the content-table row still exists
           when this method is called — the 'delete' command needs the
           ``rowid`` from the content table. Use
           :meth:`_remove_fts_by_rowid` after deletion if the row has
           already been removed.
        """
        if not self._fts_config:
            return
        row = self.db.execute_one(
            f"SELECT rowid FROM {self.table} WHERE node_id = ?", (node_id,)
        )
        if not row or row.get("rowid") is None:
            return
        self._remove_fts_by_rowid(node_id, row["rowid"])

    def _remove_fts_by_rowid(self, node_id: str, rowid: int) -> None:
        """Remove a rowid from the FTS index.

        Unlike :meth:`_remove_from_fts`, this method works **after** the
        content-table row has been deleted — it only needs the saved
        rowid.  If the ``'delete'`` command fails, a warning is logged
        rather than triggering an automatic rebuild: a rebuild at this
        point would scan the current content table (which no longer
        contains the deleted row) and produce a correct index anyway.
        """
        if not self._fts_config:
            return
        try:
            self.db.execute(
                f"INSERT INTO {self._fts_config.fts_table}"
                f"({self._fts_config.fts_table}, rowid)"
                " VALUES('delete', ?)",
                (rowid,),
            )
        except sqlite3.DatabaseError as exc:
            logger.warning(
                "FTS 'delete' failed for %s (rowid=%s): %s. "
                "FTS index may be stale — a search query will "
                "trigger a rebuild automatically.",
                node_id, rowid, exc,
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
            (node_id,),
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

    # ── FTS5 maintenance ──────────────────────────────────────────────

    def optimize_fts(self) -> None:
        """Run FTS5 OPTIMIZE on ``nodes_fts`` to rebuild the index.

        FTS5 tables accumulate internal fragmentation over time as rows
        are inserted, updated, and deleted.  Periodic optimization
        prevents progressive search-performance degradation.

        Safe to call at any time — no-op on empty/non-existent FTS.
        """
        if not self._fts_config:
            return
        config = self._fts_config
        self.db.execute(
            f"INSERT INTO {config.fts_table}({config.fts_table}) VALUES('optimize')"
        )
