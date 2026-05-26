"""Shared triple PK collision check helpers for ID rename operations.

Both NodeService and PredicateService need to check for triple PK
collisions before renaming an ID. These helpers avoid code duplication
and circular imports.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from A.data.base import SQLiteDB


def check_triple_subject_collision(
    db: "SQLiteDB", old_id: str, new_id: str,
) -> None:
    """Raise ``ValueError`` if renaming node_id ``old_id`` → ``new_id`` would
    cause a triple PK collision on ``subject_uuid``.
    """
    old_triples = db.execute(
        "SELECT predicate_id, object_value, object_type FROM triples "
        "WHERE subject_uuid = ?",
        (old_id,),
    )
    for t in old_triples:
        existing = db.execute_one(
            "SELECT 1 FROM triples WHERE subject_uuid = ? AND predicate_id = ? "
            "AND object_value = ? AND object_type = ?",
            (new_id, t["predicate_id"], t["object_value"], t["object_type"]),
        )
        if existing:
            raise ValueError(
                f"Rename would cause triple PK collision: "
                f"subject ({new_id}, {t['predicate_id']}, {t['object_value']}, {t['object_type']}) "
                f"already exists"
            )


def check_triple_object_collision(
    db: "SQLiteDB", old_id: str, new_id: str,
) -> None:
    """Raise ``ValueError`` if renaming node_id ``old_id`` → ``new_id`` would
    cause a triple PK collision on ``object_value`` (URI objects only).
    """
    old_triples = db.execute(
        "SELECT subject_uuid, predicate_id, object_type FROM triples "
        "WHERE object_type = 'uri' AND object_value = ?",
        (old_id,),
    )
    for t in old_triples:
        existing = db.execute_one(
            "SELECT 1 FROM triples WHERE subject_uuid = ? AND predicate_id = ? "
            "AND object_value = ? AND object_type = ?",
            (t["subject_uuid"], t["predicate_id"], new_id, t["object_type"]),
        )
        if existing:
            raise ValueError(
                f"Rename would cause triple PK collision: "
                f"triple ({t['subject_uuid']}, {t['predicate_id']}, {new_id}, {t['object_type']}) "
                f"already exists"
            )


def check_triple_predicate_collision(
    db: "SQLiteDB", old_id: str, new_id: str,
) -> None:
    """Raise ``ValueError`` if renaming predicate_id ``old_id`` → ``new_id`` would
    cause a triple PK collision on ``predicate_id``.
    """
    old_triples = db.execute(
        "SELECT subject_uuid, object_value, object_type FROM triples "
        "WHERE predicate_id = ?",
        (old_id,),
    )
    for t in old_triples:
        existing = db.execute_one(
            "SELECT 1 FROM triples WHERE subject_uuid = ? AND predicate_id = ? "
            "AND object_value = ? AND object_type = ?",
            (t["subject_uuid"], new_id, t["object_value"], t["object_type"]),
        )
        if existing:
            raise ValueError(
                f"Rename would cause triple PK collision: "
                f"triple ({t['subject_uuid']}, {new_id}, {t['object_value']}, {t['object_type']}) "
                f"already exists"
            )


def check_predicate_group_member_collision(
    db: "SQLiteDB", old_id: str, new_id: str,
) -> None:
    """Raise ``ValueError`` if renaming predicate_id ``old_id`` → ``new_id`` would
    cause a UNIQUE collision on ``predicate_group_members(group_uuid, predicate_id)``.
    """
    old_members = db.execute(
        "SELECT group_uuid FROM predicate_group_members WHERE predicate_id = ?",
        (old_id,),
    )
    for m in old_members:
        existing = db.execute_one(
            "SELECT 1 FROM predicate_group_members WHERE group_uuid = ? AND predicate_id = ?",
            (m["group_uuid"], new_id),
        )
        if existing:
            raise ValueError(
                f"Rename would cause predicate group member collision: "
                f"group ({m['group_uuid']}, {new_id}) already exists"
            )
