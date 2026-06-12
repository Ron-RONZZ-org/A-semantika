"""TripleService — custom service for RDF triple management.

Triples use a compound PK (subject_uuid, predicate_id, object_value, object_type)
WITHOUT ROWID — this is standard RDF triple store practice.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from A_semantika.data.storage import now


class DuplicateTripleError(ValueError):
    """Raised when attempting to add a triple that already exists.

    Subclass of ValueError so existing ``except ValueError`` handlers
    still catch it by default, but callers that want to distinguish
    duplicates from other errors can catch this type specifically.
    """
    pass


class TripleService:
    """Custom service for semantic triple CRUD and query operations.

    NOT a CRUDService subclass — triples have a compound PK and no UUID.
    """

    # Default RDF/OWL namespace prefixes for Turtle export.
    # Maps prefix → full URI. Copied to instance-level _prefix_uris on init.
    # Use register_prefix() on the instance to add custom prefixes.
    _DEFAULT_PREFIXES: dict[str, str] = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "owl": "http://www.w3.org/2002/07/owl#",
    }

    def __init__(self, db: Any) -> None:
        self.db = db
        # Instance-level copy of prefixes so register_prefix() does not
        # mutate the shared class-level dict.
        self._prefix_uris: dict[str, str] = dict(self._DEFAULT_PREFIXES)

    # ── Create ──────────────────────────────────────────────────────────

    def add(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
        object_type: str = "uri",
        object_lang: str | None = None,
        object_datatype: str | None = None,
        object_unit: str | None = None,
    ) -> dict:
        """Add a triple (subject --predicate--> object).

        Validates FK references explicitly before INSERT so that FK violations
        produce accurate error messages (not misleading "already exists").

        Args:
            subject_uuid: Full UUID of the subject node.
            predicate_id: ID of the predicate.
            object_value: Object value (UUID for URI refs, literal value for literals).
            object_type: 'uri' or 'literal'.
            object_lang: Language tag (only for string literals).
            object_datatype: XSD datatype (for typed literals).
            object_unit: Node UUID for unit of measurement.

        Returns:
            The created triple dict.

        Raises:
            ValueError: If a FK reference is invalid or the triple already exists.
        """
        # Validate FK references before INSERT
        subj = self.db.execute_one(
            "SELECT node_id FROM nodes WHERE node_id = ?", (subject_uuid,)
        )
        if not subj:
            msg = f"Subject node not found: {subject_uuid}"
            raise ValueError(msg)

        pred = self.db.execute_one(
            "SELECT predicate_id FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not pred:
            msg = f"Predicate not found: {predicate_id}"
            raise ValueError(msg)

        if object_type == "uri":
            obj = self.db.execute_one(
                "SELECT node_id FROM nodes WHERE node_id = ?", (object_value,)
            )
            if not obj:
                msg = f"Object node not found: {object_value}"
                raise ValueError(msg)

        timestamp = now()
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    """INSERT INTO triples
                       (subject_uuid, predicate_id, object_type, object_value,
                        object_lang, object_datatype, object_unit, kreita_je)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (subject_uuid, predicate_id, object_type, object_value,
                     object_lang, object_datatype, object_unit, timestamp),
                )
        except sqlite3.IntegrityError as exc:
            msg = f"Triple already exists: subject={subject_uuid}, predicate={predicate_id}, object={object_value}"
            raise DuplicateTripleError(msg) from exc

        return self.get_one(subject_uuid, predicate_id, object_value, object_type)

    # ── Update Metadata ─────────────────────────────────────────────────

    def update_metadata(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
        object_type: str = "uri",
        object_lang: str | None = None,
        object_datatype: str | None = None,
        object_unit: str | None = None,
    ) -> dict | None:
        """Update mutable metadata on an existing triple.

        Only updates non-PK columns (object_lang, object_datatype, object_unit).
        PK columns (subject_uuid, predicate_id, object_value, object_type)
        cannot change — the SPO identity is fixed. Preserves kreita_je.

        Only the columns that are explicitly provided (not None) are updated,
        so passing only ``object_lang`` does not overwrite existing
        ``object_datatype`` or ``object_unit``.

        Returns:
            The updated triple dict, or ``None`` if no columns to update.

        Raises:
            ValueError: If no matching triple is found.
        """
        set_parts: list[str] = []
        params: list = []
        if object_lang is not None:
            set_parts.append("object_lang = ?")
            params.append(object_lang)
        if object_datatype is not None:
            set_parts.append("object_datatype = ?")
            params.append(object_datatype)
        if object_unit is not None:
            set_parts.append("object_unit = ?")
            params.append(object_unit)

        if not set_parts:
            return None  # no metadata columns to update

        params.extend([subject_uuid, predicate_id, object_value, object_type])
        sql = (
            f"UPDATE triples SET {', '.join(set_parts)}"
            " WHERE subject_uuid = ? AND predicate_id = ? AND object_value = ? AND object_type = ?"
        )
        with self.db.transaction() as conn:
            conn.execute(sql, params)
        return self.get_one(subject_uuid, predicate_id, object_value, object_type)

    # ── Read ────────────────────────────────────────────────────────────

    def get_one(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
        object_type: str = "uri",
    ) -> dict | None:
        """Get a single triple by its compound key."""
        return self.db.execute_one(
            """SELECT * FROM triples
               WHERE subject_uuid = ? AND predicate_id = ? AND object_value = ? AND object_type = ?""",
            (subject_uuid, predicate_id, object_value, object_type),
        )

    def get_by_subject(self, uuid: str) -> list[dict]:
        """Get all triples where the given node is the subject."""
        return self.db.execute(
            "SELECT * FROM triples WHERE subject_uuid = ? ORDER BY predicate_id, object_value",
            (uuid,),
        )

    def get_by_predicate(self, predicate_id: str, limit: int = 100) -> list[dict]:
        """Get all triples with the given predicate."""
        return self.db.execute(
            "SELECT * FROM triples WHERE predicate_id = ? ORDER BY subject_uuid LIMIT ?",
            (predicate_id, limit),
        )

    def get_by_object(self, object_value: str, object_type: str | None = None) -> list[dict]:
        """Get all triples with the given object value."""
        if object_type:
            return self.db.execute(
                "SELECT * FROM triples WHERE object_value = ? AND object_type = ? ORDER BY subject_uuid",
                (object_value, object_type),
            )
        return self.db.execute(
            "SELECT * FROM triples WHERE object_value = ? ORDER BY subject_uuid",
            (object_value,),
        )

    def get_by_sp(self, subject_uuid: str, predicate_id: str) -> list[dict]:
        """Get triples matching (subject, predicate)."""
        return self.db.execute(
            "SELECT * FROM triples WHERE subject_uuid = ? AND predicate_id = ? ORDER BY object_value",
            (subject_uuid, predicate_id),
        )

    def get_subject_objects(self, subject_uuid: str) -> list[dict]:
        """Get all triples for a subject, with resolved object node labels.

        Returns triples with additional 'object_label' and 'object_lang' fields
        from the object node (if object_type='uri').
        """
        return self.db.execute(
            """SELECT t.*, n.etikedoj AS object_node_etikedoj
               FROM triples t
               LEFT JOIN nodes n ON t.object_node_uuid = n.node_id
               WHERE t.subject_uuid = ?
               ORDER BY t.predicate_id""",
            (subject_uuid,),
        )

    # ── Delete ──────────────────────────────────────────────────────────

    def remove(
        self,
        subject_uuid: str | None = None,
        predicate_id: str | None = None,
        object_value: str | None = None,
        object_type: str | None = None,
    ) -> int:
        """Remove triples matching the given criteria.

        All parameters are optional — use None as wildcard.
        At least one filter must be specified.

        Returns:
            Number of deleted rows.
        """
        clauses = []
        params = []

        if subject_uuid is not None:
            clauses.append("subject_uuid = ?")
            params.append(subject_uuid)
        if predicate_id is not None:
            clauses.append("predicate_id = ?")
            params.append(predicate_id)
        if object_value is not None:
            clauses.append("object_value = ?")
            params.append(object_value)
        if object_type is not None:
            clauses.append("object_type = ?")
            params.append(object_type)

        if not clauses:
            msg = "At least one filter required for triple removal"
            raise ValueError(msg)

        with self.db.transaction() as conn:
            cursor = conn.execute(
                f"DELETE FROM triples WHERE {' AND '.join(clauses)}",
                params,
            )
            return cursor.rowcount

    def remove_by_predicate(self, predicate_id: str) -> int:
        """Delete all triples with the given predicate.

        Args:
            predicate_id: The predicate to remove triples for.

        Returns:
            Number of deleted rows.
        """
        return self.remove(predicate_id=predicate_id)

    def remove_by_node(self, node_id: str) -> int:
        """Delete all triples referencing a node (as subject or URI object).

        Args:
            node_id: The node to remove triples for.

        Returns:
            Number of deleted rows.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM triples WHERE subject_uuid = ? "
                "OR (object_type = 'uri' AND object_value = ?)",
                (node_id, node_id),
            )
            return cursor.rowcount

    def get_by_node(self, node_id: str) -> list[dict]:
        """Get all triples referencing a node (as subject or URI object).

        Args:
            node_id: The node ID to fetch triples for.

        Returns:
            List of triple dicts, each with optional ``object_node_etikedoj``
            joined from the object node (if object_type='uri').
        """
        return self.db.execute(
            """SELECT t.*, n.etikedoj AS object_node_etikedoj
               FROM triples t
               LEFT JOIN nodes n ON t.object_node_uuid = n.node_id
               WHERE t.subject_uuid = ?
                  OR (t.object_type = 'uri' AND t.object_value = ?)
               ORDER BY t.predicate_id""",
            (node_id, node_id),
        )

    def get_by_nodes(self, node_ids: list[str]) -> list[dict]:
        """Get all triples referencing any of the given nodes (as subject or URI object).

        Uses a single bulk query instead of N individual ``get_by_node()``
        calls, which is significantly faster for batch operations like
        ``nodo forigi`` with multiple node IDs.

        Args:
            node_ids: Node IDs to fetch triples for.

        Returns:
            List of triple dicts.
        """
        if not node_ids:
            return []
        placeholders = ",".join("?" * len(node_ids))
        return self.db.execute(
            f"""SELECT t.*, n.etikedoj AS object_node_etikedoj
               FROM triples t
               LEFT JOIN nodes n ON t.object_node_uuid = n.node_id
               WHERE t.subject_uuid IN ({placeholders})
                  OR (t.object_type = 'uri' AND t.object_value IN ({placeholders}))
               ORDER BY t.predicate_id""",
            (*node_ids, *node_ids),
        )

    def count_by_subject_or_object(self, node_id: str) -> int:
        """Count triples referencing a node (as subject or URI object).

        Args:
            node_id: The node ID to check.

        Returns:
            Number of triples referencing the node.
        """
        row = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM triples "
            "WHERE subject_uuid = ? OR (object_type = 'uri' AND object_value = ?)",
            (node_id, node_id),
        )
        return row["cnt"] if row else 0

    # ── Multi-filter search (used by search_triples_by_labels) ──────────

    def search_triples(
        self,
        where_clause: str,
        params: list,
        order_by: str | None = None,
        limit: int = 100,
        dato_de: str | None = None,
        dato_gis: str | None = None,
    ) -> list[dict]:
        """Search triples by unified WHERE clause, with optional date filtering.
        
        Args:
            where_clause: SQL WHERE condition (e.g., "subject_uuid IN (?, ?) OR predicate_id = ?").
                         Empty string is treated as "1=1" (no restriction).
            params: Parameter values to bind to WHERE clause. Will be extended with limit
                     and optionally date params.
            order_by: SQL ORDER BY clause (e.g., "CASE ... END, subject_uuid, predicate_id").
                      If None, defaults to "subject_uuid, predicate_id".
            limit: Maximum results to return.
            dato_de: ISO 8601 start datetime (inclusive). If provided, adds
                     ``AND kreita_je >= ?`` to WHERE clause.
            dato_gis: ISO 8601 end datetime (inclusive). If provided, adds
                      ``AND kreita_je <= ?`` to WHERE clause.
        
        Returns:
            List of matching triple dicts.
        
        Raises:
            ValueError: If where_clause is None or not a string.
        """
        if not where_clause or not where_clause.strip():
            where_clause = "1=1"
        
        # Append date filters if provided.
        # Date clauses are appended after the WHERE clause, so date params
        # must come AFTER the original WHERE params in the parameter list.
        date_clauses: list[str] = []
        if dato_de is not None:
            date_clauses.append("kreita_je >= ?")
        if dato_gis is not None:
            date_clauses.append("kreita_je <= ?")
        
        full_where = f"({where_clause})" + (" AND " + " AND ".join(date_clauses) if date_clauses else "")
        
        sort_clause = order_by if order_by else "subject_uuid, predicate_id"
        sql = f"SELECT * FROM triples WHERE {full_where} ORDER BY {sort_clause} LIMIT ?"
        
        params_copy = list(params)        # original WHERE params first
        if dato_de is not None:
            params_copy.append(dato_de)
        if dato_gis is not None:
            params_copy.append(dato_gis)
        params_copy.append(limit)
        
        return self.db.execute(sql, params_copy)

    # ── Count / Stats ───────────────────────────────────────────────────

    def count(self) -> int:
        """Return total number of triples."""
        row = self.db.execute_one("SELECT COUNT(*) AS cnt FROM triples")
        return row["cnt"] if row else 0

    def get_stats(self) -> dict:
        """Return statistics about the triple store."""
        total = self.count()
        unique_predicates = self.db.execute_one(
            "SELECT COUNT(DISTINCT predicate_id) AS cnt FROM triples"
        )
        unique_subjects = self.db.execute_one(
            "SELECT COUNT(DISTINCT subject_uuid) AS cnt FROM triples"
        )
        return {
            "total_triples": total,
            "unique_predicates": unique_predicates["cnt"] if unique_predicates else 0,
            "unique_subjects": unique_subjects["cnt"] if unique_subjects else 0,
        }

    # ── Turtle Export ───────────────────────────────────────────────────

    def register_prefix(self, prefix: str, uri: str) -> None:
        """Register a custom namespace prefix for Turtle export.

        Only affects this TripleService instance (not class-level shared state).

        Args:
            prefix: The prefix (without colon), e.g. 'foaf'.
            uri: The full namespace URI, e.g. 'http://xmlns.com/foaf/0.1/'.
        """
        self._prefix_uris[prefix] = uri

    def export_turtle(self, base_uri: str = "https://example.org/") -> str:
        """Export all triples to Turtle (.ttl) format.

        Triples are grouped by subject, with predicates formatted as:
          subject
              predicate1 object1 ;
              predicate2 object2 ;
              predicate3 object3 .

        Nodes that have no outgoing triples are listed as Turtle comments
        at the end of the output so they are not silently lost.

        Args:
            base_uri: Base URI for node references.

        Returns:
            Turtle formatted string.
        """
        from A_semantika._triple_turtle import export_turtle as _export_turtle

        return _export_turtle(self.db, self._prefix_uris, base_uri)
