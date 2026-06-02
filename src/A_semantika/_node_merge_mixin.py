"""NodeMergeMixin — merge two nodes into one.

Extracted from ``_node_service.py`` to keep that file under 500 lines.
"""
from __future__ import annotations

import json
from typing import Any

from A_semantika._node_helpers import extract_difin_text, extract_label_text
from A_semantika.data.storage import now


class NodeMergeMixin:
    """Mixin that provides ``merge_nodes()`` to NodeService.

    Expects ``self.db``, ``self.get()``, ``self._fts_config``,
    ``self.table``, and ``self._index_fts()`` from the host class.
    """

    def merge_nodes(self, source_id: str, target_id: str) -> dict[str, Any]:
        """Merge source node INTO target node.

        All triples referencing *source* (as subject or URI object) are
        reassigned to *target*.  Triple PK conflicts (where *target* already
        has the same subject-predicate-object-type combination) are silently
        skipped — target wins.

        Labels and definitions are merged with target-first precedence:
        source languages that do not exist in target are added; target
        values are kept on collision.

        The source node is deleted after reassignment.  ALL operations
        happen in a single transaction with deferred FK checks.

        Args:
            source_id: Node ID of the source (will be deleted).
            target_id: Node ID of the target (survives).

        Returns:
            Updated target node dict.

        Raises:
            ValueError: If either node is not found, or *source_id* equals
                *target_id*.
        """
        if source_id == target_id:
            raise ValueError("Source and target must be different nodes")

        source = self.get(source_id)
        if not source:
            raise ValueError(f"Source node not found: {source_id}")

        target = self.get(target_id)
        if not target:
            raise ValueError(f"Target node not found: {target_id}")

        # Compute merged labels / definitions (target-first)
        try:
            source_labels: dict = (
                json.loads(source["etikedoj"])
                if isinstance(source["etikedoj"], str)
                else source["etikedoj"]
            )
        except (json.JSONDecodeError, TypeError):
            source_labels = {}
        try:
            target_labels: dict = (
                json.loads(target["etikedoj"])
                if isinstance(target["etikedoj"], str)
                else target["etikedoj"]
            )
        except (json.JSONDecodeError, TypeError):
            target_labels = {}
        try:
            source_defns: dict = (
                json.loads(source["difinoj"])
                if isinstance(source["difinoj"], str)
                else source["difinoj"]
            )
        except (json.JSONDecodeError, TypeError):
            source_defns = {}
        try:
            target_defns: dict = (
                json.loads(target["difinoj"])
                if isinstance(target["difinoj"], str)
                else target["difinoj"]
            )
        except (json.JSONDecodeError, TypeError):
            target_defns = {}

        merged_labels = {**source_labels, **target_labels}  # target wins
        merged_defns = {**source_defns, **target_defns}

        # Save rowids BEFORE transaction for FTS cleanup
        source_rowid: int | None = None
        target_rowid: int | None = None
        if self._fts_config:
            row = self.db.execute_one(
                "SELECT rowid FROM nodes WHERE node_id = ?", (source_id,)
            )
            source_rowid = row["rowid"] if row else None
            row = self.db.execute_one(
                "SELECT rowid FROM nodes WHERE node_id = ?", (target_id,)
            )
            target_rowid = row["rowid"] if row else None

        now_ts = now()

        with self.db.transaction() as conn:
            conn.execute("PRAGMA defer_foreign_keys=ON")

            # 0. Delete old FTS entries BEFORE any content changes
            if self._fts_config:
                if source_rowid is not None:
                    conn.execute(
                        f"INSERT INTO {self._fts_config.fts_table}"
                        f"({self._fts_config.fts_table}, rowid)"
                        " VALUES('delete', ?)",
                        (source_rowid,),
                    )
                if target_rowid is not None:
                    conn.execute(
                        f"INSERT INTO {self._fts_config.fts_table}"
                        f"({self._fts_config.fts_table}, rowid)"
                        " VALUES('delete', ?)",
                        (target_rowid,),
                    )

            # 1. Update target node with merged labels / definitions
            conn.execute(
                "UPDATE nodes SET etikedoj = ?, label_text = ?, difinoj = ?, "
                "difin_text = ?, modifita_je = ? WHERE node_id = ?",
                (
                    json.dumps(merged_labels),
                    extract_label_text(merged_labels),
                    json.dumps(merged_defns),
                    extract_difin_text(merged_defns),
                    now_ts,
                    target_id,
                ),
            )

            # 2. Reassign triples where source is subject → target.
            #    Skip triples that would collide with target's (P, O, T).
            conn.execute(
                """UPDATE triples SET subject_uuid = ?
                   WHERE subject_uuid = ?
                     AND (predicate_id, object_value, object_type) NOT IN (
                       SELECT predicate_id, object_value, object_type
                       FROM triples WHERE subject_uuid = ?
                     )""",
                (target_id, source_id, target_id),
            )

            # 3. Reassign triples where source is URI object → target.
            #    Skip triples that would collide with target's (S, P, T).
            conn.execute(
                """UPDATE triples SET object_value = ?
                   WHERE object_type = 'uri' AND object_value = ?
                     AND (subject_uuid, predicate_id, object_type) NOT IN (
                       SELECT subject_uuid, predicate_id, object_type
                       FROM triples WHERE object_type = 'uri' AND object_value = ?
                     )""",
                (target_id, source_id, target_id),
            )
            # object_node_uuid auto-recomputes (generated column)

            # 4. Clean up skipped triples that still reference source.
            #    Steps 2-3 only reassigned non-colliding triples; the
            #    colliding ones still reference source and must be
            #    deleted before the source node can be removed.
            conn.execute(
                "DELETE FROM triples WHERE subject_uuid = ? "
                "OR (object_type = 'uri' AND object_value = ?)",
                (source_id, source_id),
            )

            # 5. Delete source node
            conn.execute(
                "DELETE FROM nodes WHERE node_id = ?", (source_id,)
            )

            # 6. Re-index target FTS.
            #    Inline the FTS insert here instead of calling
            #    self._index_fts() which uses self.db.execute() and would
            #    trigger an implicit commit — breaking the transaction.
            if self._fts_config:
                target_entry = conn.execute(
                    f"SELECT rowid, node_id, "
                    f"{', '.join(self._fts_config.fts_columns)} "
                    f"FROM {self.table} WHERE node_id = ?",
                    (target_id,),
                ).fetchone()
                if target_entry:
                    values: list[Any] = [target_entry[0], target_entry[1]]
                    for i, col in enumerate(self._fts_config.fts_columns):
                        col_idx = i + 2  # skip rowid (0) and node_id (1)
                        val = target_entry[col_idx]
                        if col in self._fts_config.normalize:
                            val = self._fts_config.normalize[col](val)
                        values.append(val)
                    placeholders = ", ".join(
                        ["?"] * (len(self._fts_config.fts_columns) + 2)
                    )
                    fts_cols = ", ".join(["node_id"] + self._fts_config.fts_columns)
                    conn.execute(
                        f"INSERT INTO {self._fts_config.fts_table} "
                        f"(rowid, {fts_cols}) VALUES ({placeholders})",
                        values,
                    )

        return self.get(target_id)
