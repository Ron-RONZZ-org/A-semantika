"""PredicateService — CRUDService subclass for predicate management.

Predicates are lightweight metadata (no undo/trash needed).
Stores multilingual labels/descriptions as JSON columns, matching
the nodes pattern (etikedoj / priskriboj).
"""
from __future__ import annotations

import json
import uuid as _uuid
from typing import Any

from A.core.service import CRUDService
from A_semantika.data.storage import now


def _ensure_json(val: Any) -> str:
    """Serialize a dict to JSON, or return as-is if already a string."""
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


def _label_from_etikedoj(etikedoj: str | dict, langs: tuple[str, ...] = ("eo", "en")) -> str:
    """Extract a single display label from etikedoj JSON.

    Tries language codes in order, falls back to first available.
    """
    try:
        labels = json.loads(etikedoj) if isinstance(etikedoj, str) else etikedoj
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(labels, dict):
        return ""
    for lang in langs:
        val = labels.get(lang)
        if val and isinstance(val, str):
            return val
    for val in labels.values():
        if val and isinstance(val, str):
            return val
    return ""


class PredicateService(CRUDService):
    """Service for managing semantic predicates.

    No undo/trash (predicates are lightweight metadata).
    Uses simple LIKE search on JSON text fields (acceptable for small tables).
    """

    def __init__(self, db: Any) -> None:
        super().__init__(
            db=db,
            table="predicates",
            undo_size=0,
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
        priskriboj = _ensure_json(data.get("priskriboj", {}))

        raw = {
            "uuid": str(_uuid.uuid4()),
            "predicate_id": predicate_id,
            "source": data.get("source", "manual"),
            "etikedoj": etikedoj,
            "priskriboj": priskriboj,
            "aliases": _ensure_json(data.get("aliases", [])),
            "kreita_je": now(),
            "modifita_je": now(),
        }

        self.db.execute(
            """INSERT INTO predicates
               (uuid, predicate_id, source, etikedoj, priskriboj, aliases, kreita_je, modifita_je)
               VALUES (:uuid, :predicate_id, :source, :etikedoj, :priskriboj, :aliases, :kreita_je, :modifita_je)""",
            raw,
        )
        return self.get(raw["uuid"])

    def update(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a predicate.

        If etikedoj or priskriboj is a dict, it is serialized to JSON.
        """
        old = self.get(uuid)
        if not old:
            msg = f"Predicate not found: {uuid}"
            raise ValueError(msg)

        updates = dict(data)

        if "etikedoj" in updates:
            updates["etikedoj"] = _ensure_json(updates["etikedoj"])
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
        params.append(uuid)

        sql = f"UPDATE predicates SET {', '.join(set_parts)} WHERE uuid = ?"
        self.db.execute(sql, params)
        return self.get(uuid)

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Search predicates across predicate_id and JSON text fields.

        Searches predicate_id, etikedoj, priskriboj, and aliases via LIKE.
        """
        if not query or not query.strip():
            return self.list(limit=limit)

        like_sql = """
            SELECT * FROM predicates
            WHERE predicate_id LIKE ?
               OR etikedoj LIKE ?
               OR priskriboj LIKE ?
               OR aliases LIKE ?
            LIMIT ?
        """
        pattern = f"%{query}%"
        return self.db.execute(like_sql, (pattern, pattern, pattern, pattern, limit))