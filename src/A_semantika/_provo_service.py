"""ProvoService — RDF reification for attaching proofs to triples.

A "proof" is represented as an RDF reification: a statement node
(rdf:type rdf:Statement) with rdf:subject, rdf:predicate, rdf:object
pointing to the target arc, plus a :hasProof literal containing the
proof text.

This service handles creation, discovery, and teardown of these
reification structures.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from A_semantika.data.storage import KATEX_DATATYPE, now


# A custom datatype URI for markdown proof text.
# Stored in object_datatype to distinguish from plain string literals.
PROOF_DATATYPE = "text/markdown"


class ProvoService:
    """Service for RDF reification of proofs on triples.

    Each proof is 1 node + 5 triples:
      - Node (rdf:Statement)
      - :hasProof (proof text literal)
      - rdf:type rdf:Statement
      - rdf:subject <target_subject>
      - rdf:predicate <target_predicate>
      - rdf:object <target_object>
    """

    def __init__(self, db: Any, triple_svc: Any, node_svc: Any, pred_svc: Any) -> None:
        self.db = db
        self.triple_svc = triple_svc
        self.node_svc = node_svc
        self.pred_svc = pred_svc

    # ── Public API ────────────────────────────────────────────────────

    def create_proof(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
        object_type: str,
        proof_text: str,
        lingvo: str | None = None,
    ) -> dict[str, Any]:
        """Create a reified proof for the given triple.

        If a proof already exists for this arc, it is replaced (upsert
        semantics — the existing statement node is reused and its
        :hasProof value is updated).

        Returns:
            Dict with keys: 'stmt_node_id', 'proof_node_id', 'created'.

        Raises:
            ValueError: If the target triple does not exist or any FK
                reference is invalid.
        """
        # Validate the target arc exists
        existing_triple = self.triple_svc.get_one(
            subject_uuid, predicate_id, object_value, object_type,
        )
        if not existing_triple:
            msg = (
                f"Target arc not found: "
                f"{subject_uuid} --{predicate_id}--> {object_value}"
            )
            raise ValueError(msg)

        # Check if a reification already exists for this arc
        stmt_node_id = self._find_reification_node(
            subject_uuid, predicate_id, object_value,
        )
        created = False

        if stmt_node_id:
            # Reuse existing statement node, update proof text
            self._upsert_proof_triple(stmt_node_id, proof_text, lingvo)
        else:
            # Create new statement node + all 5 reification triples
            stmt_node_id = self._create_reification(
                subject_uuid, predicate_id, object_value, object_type,
                proof_text, lingvo,
            )
            created = True

        return {
            "stmt_node_id": stmt_node_id,
            "created": created,
        }

    def find_proofs(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
    ) -> list[dict[str, Any]]:
        """Find all proofs attached to the given arc.

        Returns:
            List of dicts with 'stmt_node_id' (the reification statement
            node) and 'proof_text' (the :hasProof literal value).
            Empty list if no proofs exist.
        """
        rows = self.db.execute(
            """SELECT stmt.subject_uuid AS stmt_node_id,
                      proof.object_value   AS proof_text,
                      proof.object_lang    AS proof_lang,
                      proof.object_datatype AS proof_datatype
               FROM triples stmt
               JOIN triples r_subj
                 ON stmt.subject_uuid = r_subj.subject_uuid
                AND r_subj.predicate_id = 'rdf:subject'
                AND r_subj.object_value = ?
               JOIN triples r_pred
                 ON stmt.subject_uuid = r_pred.subject_uuid
                AND r_pred.predicate_id = 'rdf:predicate'
                AND r_pred.object_value = ?
               JOIN triples r_obj
                 ON stmt.subject_uuid = r_obj.subject_uuid
                AND r_obj.predicate_id = 'rdf:object'
                AND r_obj.object_value = ?
               LEFT JOIN triples proof
                 ON stmt.subject_uuid = proof.subject_uuid
                AND proof.predicate_id = ':hasProof'
               WHERE stmt.predicate_id = 'rdf:type'
                 AND stmt.object_value = 'rdf:Statement'
               ORDER BY stmt.kreita_je ASC""",
            (subject_uuid, predicate_id, object_value),
        )
        return rows

    def delete_proof(self, stmt_node_id: str) -> bool:
        """Delete a proof (statement node + all reification triples).

        Args:
            stmt_node_id: The node_id of the rdf:Statement node.

        Returns:
            True if the proof was deleted, False if not found.
        """
        # Verify the node exists and is a statement node
        node = self.node_svc.get(stmt_node_id)
        if not node:
            return False

        # Delete all triples where stmt is the subject (all 5 arcs)
        self.triple_svc.remove(subject_uuid=stmt_node_id)

        # Hard-delete the statement node (no trash — statement exists
        # only to host the proof)
        self.node_svc.delete(stmt_node_id, soft=False)
        return True

    def cascade_delete_proofs(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
    ) -> int:
        """Cascade-delete all reified proofs for a given arc.

        Finds all reification statement nodes pointing to the given
        SPO combination, and tears them down (node + 5 arcs each).

        Called before deleting a triple to avoid orphan proofs.

        Returns:
            Number of proofs deleted.
        """
        proofs = self.find_proofs(subject_uuid, predicate_id, object_value)
        deleted = 0
        for proof in proofs:
            stmt_id = proof["stmt_node_id"]
            try:
                self.delete_proof(stmt_id)
                deleted += 1
            except Exception:
                pass  # Continue with remaining proofs
        return deleted

    def get_all_proofs_batch(self) -> list[dict[str, Any]]:
        """Batch query: find ALL reifications across the entire triple store.

        Returns one row per proof with the arc components and the statement
        node ID. Used by ``serci`` to annotate results with proof presence.

        Returns:
            List of dicts with keys: s (subject), p (predicate), o (object),
            stmt_node (statement node_id).
        """
        return self.db.execute(
            """SELECT r_subj.object_value AS s,
                      r_pred.object_value AS p,
                      r_obj.object_value   AS o,
                      stmt.subject_uuid    AS stmt_node
               FROM triples stmt
               JOIN triples r_subj
                 ON stmt.subject_uuid = r_subj.subject_uuid
                AND r_subj.predicate_id = 'rdf:subject'
               JOIN triples r_pred
                 ON stmt.subject_uuid = r_pred.subject_uuid
                AND r_pred.predicate_id = 'rdf:predicate'
               JOIN triples r_obj
                 ON stmt.subject_uuid = r_obj.subject_uuid
                AND r_obj.predicate_id = 'rdf:object'
               WHERE stmt.predicate_id = 'rdf:type'
                 AND stmt.object_value = 'rdf:Statement'"""
        )

    def get_proofs_for_arcs_batch(
        self, arcs: list[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], list[str]]:
        """Batch query: find all proofs for a given set of arcs.

        Args:
            arcs: List of (subject_uuid, predicate_id, object_value) tuples.

        Returns:
            Dict mapping each arc key to a list of statement node IDs.
            Arcs without proofs are omitted from the dict.
        """
        if not arcs:
            return {}

        # Build a large IN clause with all arc components.
        # We query all reifications, then filter in Python.
        all_proofs = self.get_all_proofs_batch()
        arc_set = set(arcs)
        result: dict[tuple[str, str, str], list[str]] = {}
        for row in all_proofs:
            key = (row["s"], row["p"], row["o"])
            if key in arc_set:
                result.setdefault(key, []).append(row["stmt_node"])
        return result

    # ── Internal helpers ──────────────────────────────────────────────

    def _generate_stmt_node_id(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
    ) -> str:
        """Generate a deterministic node ID for the reification statement.

        Format:  PROVO_{subj}__{pred_sanitized}__{obj}
        with collision resolution: _2, _3, etc.

        Predicate IDs (e.g. ``:estas_speciala_kazo``, ``rdf:type``)
        are sanitized by stripping leading colon and replacing colons
        with underscores.
        """
        # Sanitize predicate_id: strip leading :, replace : with _
        pred_safe = predicate_id.lstrip(":").replace(":", "_")
        # Build candidate ID
        base = f"PROVO_{subject_uuid}__{pred_safe}__{object_value}"
        # Normalize: strip non-ASCII, collapse non-alnum
        nfkd = unicodedata.normalize("NFKD", base)
        ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_str)
        safe = safe.strip("_").upper()

        if not safe:
            safe = "PROVO"

        # Collision resolution: try _2, _3, ... _99 then fallback to UUID
        candidate = safe
        counter = 2
        while self.node_svc.get(candidate):
            if counter > 99:
                import uuid as _uuid
                candidate = f"PROVO_{_uuid.uuid4().hex[:8].upper()}"
                break
            candidate = f"{safe}_{counter}"
            counter += 1

        return candidate

    def _find_reification_node(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
    ) -> str | None:
        """Find an existing reification statement node for the given arc.

        Returns the statement node_id, or None if no reification exists.
        """
        row = self.db.execute_one(
            """SELECT stmt.subject_uuid AS stmt_node
               FROM triples stmt
               JOIN triples r_subj
                 ON stmt.subject_uuid = r_subj.subject_uuid
                AND r_subj.predicate_id = 'rdf:subject'
                AND r_subj.object_value = ?
               JOIN triples r_pred
                 ON stmt.subject_uuid = r_pred.subject_uuid
                AND r_pred.predicate_id = 'rdf:predicate'
                AND r_pred.object_value = ?
               JOIN triples r_obj
                 ON stmt.subject_uuid = r_obj.subject_uuid
                AND r_obj.predicate_id = 'rdf:object'
                AND r_obj.object_value = ?
               WHERE stmt.predicate_id = 'rdf:type'
                 AND stmt.object_value = 'rdf:Statement'
               LIMIT 1""",
            (subject_uuid, predicate_id, object_value),
        )
        return row["stmt_node"] if row else None

    def _create_reification(
        self,
        subject_uuid: str,
        predicate_id: str,
        object_value: str,
        object_type: str,
        proof_text: str,
        lingvo: str | None = None,
    ) -> str:
        """Create a full reification: statement node + 5 triples.

        Everything happens in a single transaction.
        """
        stmt_node_id = self._generate_stmt_node_id(
            subject_uuid, predicate_id, object_value,
        )
        timestamp = now()

        with self.db.transaction() as conn:
            # 1. Create the statement node with a descriptive label
            subj_label = self._get_node_label(subject_uuid)
            obj_label = self._get_node_label(object_value) if object_type == "uri" else object_value
            pred_label = self._get_predicate_label(predicate_id)
            stmt_label = f"Provo: {subj_label} {pred_label} {obj_label}"
            import json
            conn.execute(
                "INSERT INTO nodes (node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
                "VALUES (?, ?, '', '{}', '', ?, ?)",
                (stmt_node_id, json.dumps({"eo": stmt_label}), timestamp, timestamp),
            )

            # 2. rdf:type rdf:Statement
            conn.execute(
                "INSERT INTO triples (subject_uuid, predicate_id, object_type, object_value, kreita_je) "
                "VALUES (?, 'rdf:type', 'uri', 'rdf:Statement', ?)",
                (stmt_node_id, timestamp),
            )

            # 3. rdf:subject
            conn.execute(
                "INSERT INTO triples (subject_uuid, predicate_id, object_type, object_value, kreita_je) "
                "VALUES (?, 'rdf:subject', 'uri', ?, ?)",
                (stmt_node_id, subject_uuid, timestamp),
            )

            # 4. rdf:predicate (stored as literal since the predicate may
            # not exist as a node in the nodes table)
            conn.execute(
                "INSERT INTO triples (subject_uuid, predicate_id, object_type, object_value, kreita_je) "
                "VALUES (?, 'rdf:predicate', 'literal', ?, ?)",
                (stmt_node_id, predicate_id, timestamp),
            )

            # 5. rdf:object (use the same object_type as the target triple
            # so that URI objects get FK validation and literals don't)
            conn.execute(
                "INSERT INTO triples (subject_uuid, predicate_id, object_type, object_value, kreita_je) "
                "VALUES (?, 'rdf:object', ?, ?, ?)",
                (stmt_node_id, object_type, object_value, timestamp),
            )

            # 6. :hasProof (the proof text itself)
            conn.execute(
                "INSERT INTO triples (subject_uuid, predicate_id, object_type, object_value, object_lang, object_datatype, kreita_je) "
                "VALUES (?, ':hasProof', 'literal', ?, ?, ?, ?)",
                (stmt_node_id, proof_text, lingvo, PROOF_DATATYPE, timestamp),
            )

        # Index the new node in FTS after transaction
        try:
            self.node_svc._index_fts(stmt_node_id)
        except Exception:
            pass  # Non-critical — the node is in the DB

        return stmt_node_id

    def _upsert_proof_triple(
        self,
        stmt_node_id: str,
        proof_text: str,
        lingvo: str | None = None,
    ) -> None:
        """Update or insert the :hasProof triple on an existing statement node."""
        timestamp = now()

        # Check if :hasProof already exists
        existing = self.db.execute_one(
            "SELECT 1 FROM triples WHERE subject_uuid = ? AND predicate_id = ':hasProof'",
            (stmt_node_id,),
        )
        if existing:
            self.db.execute(
                "UPDATE triples SET object_value = ?, object_lang = ?, object_datatype = ? "
                "WHERE subject_uuid = ? AND predicate_id = ':hasProof'",
                (proof_text, lingvo, PROOF_DATATYPE, stmt_node_id),
            )
        else:
            self.db.execute(
                "INSERT INTO triples (subject_uuid, predicate_id, object_type, object_value, object_lang, object_datatype, kreita_je) "
                "VALUES (?, ':hasProof', 'literal', ?, ?, ?, ?)",
                (stmt_node_id, proof_text, lingvo, PROOF_DATATYPE, timestamp),
            )

    def _get_node_label(self, node_id: str) -> str:
        """Get a short display label for a node, or fall back to node_id."""
        node = self.node_svc.get(node_id)
        if not node:
            return node_id[:16]
        from A_semantika._node_helpers import get_label_from_node
        return get_label_from_node(node)

    def _get_predicate_label(self, predicate_id: str) -> str:
        """Get a short display label for a predicate."""
        pred = self.pred_svc.get_by_predicate_id(predicate_id)
        if not pred:
            return predicate_id
        from A_semantika._node_helpers import get_label_from_node
        return get_label_from_node(pred)
