"""TripleService — custom service for RDF triple management.

Triples use a compound PK (subject_uuid, predicate_id, object_value, object_type)
WITHOUT ROWID — this is standard RDF triple store practice.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from A_semantika.data.storage import now


class TripleService:
    """Custom service for semantic triple CRUD and query operations.

    NOT a CRUDService subclass — triples have a compound PK and no UUID.
    """

    def __init__(self, db: Any) -> None:
        self.db = db

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
            ValueError: If the triple already exists (duplicate PK).
        """
        if self.exists(subject_uuid, predicate_id, object_value, object_type):
            msg = "Triple already exists"
            raise ValueError(msg)

        timestamp = now()
        try:
            self.db.execute(
                """INSERT INTO triples
                   (subject_uuid, predicate_id, object_type, object_value,
                    object_lang, object_datatype, object_unit, kreita_je)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (subject_uuid, predicate_id, object_type, object_value,
                 object_lang, object_datatype, object_unit, timestamp),
            )
        except Exception as exc:
            # SQLite constraint violation (e.g. FK)
            msg = f"Failed to add triple: {exc}"
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
               LEFT JOIN nodes n ON t.object_node_uuid = n.uuid
               WHERE t.subject_uuid = ?
               ORDER BY t.predicate_id""",
            (subject_uuid,),
        )

    def exists(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
        object_type: str = "uri",
    ) -> bool:
        """Check if a triple exists."""
        row = self.db.execute_one(
            "SELECT 1 FROM triples WHERE subject_uuid = ? AND predicate_id = ? AND object_value = ? AND object_type = ?",
            (subject_uuid, predicate_id, object_value, object_type),
        )
        return row is not None

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

    def export_turtle(self, base_uri: str = "https://example.org/") -> str:
        """Export all triples to Turtle (.ttl) format.

        Args:
            base_uri: Base URI for node references.

        Returns:
            Turtle formatted string.
        """
        lines = [
            "@prefix : <{base}> .".format(base=base_uri),
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "",
        ]

        triples = self.db.execute(
            """SELECT t.*, n.etikedoj AS subj_label, p.label_en AS pred_label
               FROM triples t
               JOIN nodes n ON t.subject_uuid = n.uuid
               JOIN predicates p ON t.predicate_id = p.predicate_id
               ORDER BY t.subject_uuid, t.predicate_id"""
        )

        current_subject = None
        for t in triples:
            subj_uri = f":{t['subject_uuid']}"
            pred_uri = f":{t['predicate_id']}"

            if t["object_type"] == "uri":
                obj = f":{t['object_value']}"
            elif t["object_datatype"]:
                # Typed literal
                escaped_val = t["object_value"].replace("\\", "\\\\").replace('"', '\\"')
                obj = f'"{escaped_val}"^^xsd:{t["object_datatype"].split(":")[-1]}'
            elif t["object_lang"]:
                escaped_val = t["object_value"].replace("\\", "\\\\").replace('"', '\\"')
                obj = f'"{escaped_val}"@{t["object_lang"]}'
            else:
                escaped_val = t["object_value"].replace("\\", "\\\\").replace('"', '\\"')
                obj = f'"{escaped_val}"'

            if t["subject_uuid"] != current_subject:
                lines.append(f"{subj_uri}")
                current_subject = t["subject_uuid"]
                lines.append(f"    {pred_uri} {obj} ;")
            else:
                lines.append(f"    {pred_uri} {obj} ;")

        # Replace trailing ' ;' with ' .' on last predicate of each subject
        result = "\n".join(lines)
        # Simple fix: append a final '.'
        if lines and lines[-1].endswith(";"):
            result = result.rstrip(";") + "."
        return result
