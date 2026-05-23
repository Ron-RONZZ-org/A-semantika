"""PredicateGroupService — CRUDService subclass for predicate group management.

Groups are named collections of predicates. No undo/trash needed.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

from A.core.service import CRUDService


class PredicateGroupService(CRUDService):
    """Service for managing predicate groups and their members.

    No undo/trash (groups are lightweight metadata containers).
    """

    def __init__(self, db: Any) -> None:
        super().__init__(
            db=db,
            table="predicate_groups",
            undo_size=0,
        )

    # ── Custom rename (group_name is the user-facing identifier) ────────

    def rename(self, old_name: str, new_name: str) -> dict:
        """Rename a predicate group.

        Args:
            old_name: Current group_name.
            new_name: New group_name.

        Returns:
            The updated group record.

        Raises:
            ValueError: If old_name not found or new_name already exists.
        """
        group = self.get_by_field("group_name", old_name)
        if not group:
            msg = f"Group not found: {old_name}"
            raise ValueError(msg)

        existing = self.get_by_field("group_name", new_name)
        if existing:
            msg = f"Group already exists: {new_name}"
            raise ValueError(msg)

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE predicate_groups SET group_name = ?, modifita_je = ? WHERE uuid = ?",
            (new_name, now, group["uuid"]),
        )
        return self.get(group["uuid"])

    # ── Member management ───────────────────────────────────────────────

    def add_member(self, group_name: str, predicate_id: str) -> dict:
        """Add a predicate to a group.

        Args:
            group_name: Name of the target group.
            predicate_id: Predicate ID to add.

        Returns:
            The new member record.

        Raises:
            ValueError: If group or predicate not found, or duplicate.
        """
        group = self.get_by_field("group_name", group_name)
        if not group:
            msg = f"Group not found: {group_name}"
            raise ValueError(msg)

        pred = self.db.execute_one(
            "SELECT predicate_id FROM predicates WHERE predicate_id = ?",
            (predicate_id,),
        )
        if not pred:
            msg = f"Predicate not found: {predicate_id}"
            raise ValueError(msg)

        # Check duplicate
        existing = self.db.execute_one(
            "SELECT uuid FROM predicate_group_members WHERE group_uuid = ? AND predicate_id = ?",
            (group["uuid"], predicate_id),
        )
        if existing:
            msg = f"Predicate '{predicate_id}' is already in group '{group_name}'"
            raise ValueError(msg)

        member_uuid = str(_uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO predicate_group_members (uuid, group_uuid, predicate_id, kreita_je) "
            "VALUES (?, ?, ?, ?)",
            (member_uuid, group["uuid"], predicate_id, now),
        )
        return {
            "uuid": member_uuid,
            "group_uuid": group["uuid"],
            "predicate_id": predicate_id,
            "kreita_je": now,
        }

    def remove_member(self, group_name: str, predicate_id: str) -> bool:
        """Remove a predicate from a group.

        Args:
            group_name: Name of the group.
            predicate_id: Predicate ID to remove.

        Returns:
            True if a row was deleted, False otherwise.
        """
        group = self.get_by_field("group_name", group_name)
        if not group:
            return False

        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM predicate_group_members WHERE group_uuid = ? AND predicate_id = ?",
                (group["uuid"], predicate_id),
            )
            return cursor.rowcount > 0

    def clear_members(self, group_uuid: str) -> None:
        """Delete all members of a group.

        Args:
            group_uuid: UUID of the group whose members to clear.
        """
        self.db.execute(
            "DELETE FROM predicate_group_members WHERE group_uuid = ?",
            (group_uuid,),
        )

    def list_members(self, group_name: str) -> list[dict]:
        """List all predicates in a group.

        Returns member records with joined predicate data.
        """
        group = self.get_by_field("group_name", group_name)
        if not group:
            return []

        return self.db.execute(
            """SELECT pgm.*, p.etikedoj, p.source
               FROM predicate_group_members pgm
               JOIN predicates p ON pgm.predicate_id = p.predicate_id
               WHERE pgm.group_uuid = ?
               ORDER BY p.predicate_id""",
            (group["uuid"],),
        )
