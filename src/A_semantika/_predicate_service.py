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
from typing import Any

from A.core.service import CRUDService
from A_semantika._constants import FTS5_KEYWORDS as _FTS5_KEYWORDS
from A_semantika.data.storage import label_from_json, now


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


def _extract_label_text(etikedoj: str | dict) -> str:
    """Extract a plain-text search string from etikedoj JSON.

    Concatenates all label values into a space-separated string for FTS indexing.
    """
    try:
        labels = json.loads(etikedoj) if isinstance(etikedoj, str) else etikedoj
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(labels, dict):
        return ""
    texts: list[str] = []
    for val in labels.values():
        if val and isinstance(val, str):
            texts.append(val)
    return " ".join(texts)





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
        count = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM predicates_fts"
        )
        if count and count["cnt"] == 0:
            self.db.execute(
                "INSERT INTO predicates_fts(predicates_fts) VALUES('rebuild')"
            )

    def _remove_from_fts(self, predicate_id: str) -> None:
        """Remove a predicate from FTS index.

        Uses FTS5 'delete' command for SQLite >= 3.50 compatibility.
        """
        row = self.db.execute_one(
            "SELECT rowid FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not row or row.get("rowid") is None:
            return
        self.db.execute(
            "INSERT INTO predicates_fts(predicates_fts, rowid)"
            " VALUES('delete', ?)",
            (row["rowid"],),
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
            "label_text": _extract_label_text(data.get("etikedoj", {})),
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
            updates["label_text"] = _extract_label_text(etikedoj_val)
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
        self.db.execute(sql, params)

        # Re-index FTS (remove old, insert new)
        self._remove_from_fts(predicate_id)
        self._index_fts(predicate_id)

        return self.get_by_predicate_id(predicate_id)

    def delete(self, predicate_id: str, soft: bool = True) -> None:
        """Hard-delete a predicate by predicate_id.

        Predicates are lightweight metadata — undo/trash are not needed.
        The ``soft`` parameter is accepted for API compatibility but
        ignored (deletion is always permanent).
        """
        self._remove_from_fts(predicate_id)
        if soft:
            from A import warning as _warn
            _warn(
                "PredicateService.delete(soft=True) is ignored — "
                "predicates are always hard-deleted."
            )
        self.db.execute(
            "DELETE FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitize a user query string for FTS5 MATCH.

        Strips special characters that can crash FTS5, but treats
        FTS5 keywords (AND, OR, NOT) as regular content by lowercasing.
        """
        safe_tokens = []
        for word in query.strip().split():
            cleaned = "".join(c for c in word if c.isalnum() or c in ("_", "."))
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
