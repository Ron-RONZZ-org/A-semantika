"""TripleService — custom service for RDF triple management.

Triples use a compound PK (subject_uuid, predicate_id, object_value, object_type)
WITHOUT ROWID — this is standard RDF triple store practice.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from A_semantika.data.storage import now


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
            msg = "Triple already exists"
            raise ValueError(msg) from exc

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
        subject_uuids: list[str] | None = None,
        predicate_ids: list[str] | None = None,
        object_values: list[str] | None = None,
        object_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Search triples by pre-resolved lists.

        Within each list the condition is OR; across lists it is AND.
        None means 'no restriction' for that parameter.

        Args:
            subject_uuids: List of subject UUIDs to match (OR).
            predicate_ids: List of predicate IDs to match (OR).
            object_values: List of object values to match (OR).
            object_types: List of object types to match (OR).
            limit: Maximum number of results.

        Returns:
            List of matching triple dicts.
        """
        clauses: list[str] = []
        params: list[str] = []

        if subject_uuids is not None:
            if not subject_uuids:
                return []
            placeholders = ",".join("?" * len(subject_uuids))
            clauses.append(f"subject_uuid IN ({placeholders})")
            params.extend(subject_uuids)

        if predicate_ids is not None:
            if not predicate_ids:
                return []
            placeholders = ",".join("?" * len(predicate_ids))
            clauses.append(f"predicate_id IN ({placeholders})")
            params.extend(predicate_ids)

        if object_values is not None:
            if not object_values:
                return []
            placeholders = ",".join("?" * len(object_values))
            clauses.append(f"object_value IN ({placeholders})")
            params.extend(object_values)

        if object_types is not None:
            if not object_types:
                return []
            placeholders = ",".join("?" * len(object_types))
            clauses.append(f"object_type IN ({placeholders})")
            params.extend(object_types)

        where_clause = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM triples WHERE {where_clause} ORDER BY subject_uuid, predicate_id LIMIT ?"
        params.append(limit)

        return self.db.execute(sql, params)

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
