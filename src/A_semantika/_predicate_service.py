"""PredicateService — CRUDService subclass for predicate management.

Predicates are lightweight metadata (no undo/trash needed).
"""
from __future__ import annotations

from typing import Any

from A.core.service import CRUDService


class PredicateService(CRUDService):
    """Service for managing semantic predicates.

    No undo/trash (predicates are lightweight metadata).
    Uses simple LIKE search (FTS is not needed for the small number of predicates).
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

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Search predicates across label/description fields via LIKE.

        Searches predicate_id, label_en, label_eo, and priskribo.
        """
        if not query or not query.strip():
            return self.list(limit=limit)

        like_sql = """
            SELECT * FROM predicates
            WHERE predicate_id LIKE ?
               OR label_en LIKE ?
               OR label_eo LIKE ?
               OR priskribo LIKE ?
            LIMIT ?
        """
        pattern = f"%{query}%"
        return self.db.execute(like_sql, (pattern, pattern, pattern, pattern, limit))
