"""Tests for PredicateGroupService — CRUD, rename, member management."""
from __future__ import annotations

import pytest


class TestGroupCreate:
    """Group creation tests."""

    def test_create_group(self, group_svc) -> None:
        """Creating a group should work."""
        group = group_svc.create({"group_name": "biologio"})
        assert group["group_name"] == "biologio"
        assert group["uuid"] is not None

    def test_create_duplicate_raises(self, group_svc) -> None:
        """Duplicate group name should raise."""
        group_svc.create({"group_name": "biologio"})
        with pytest.raises(Exception):
            group_svc.create({"group_name": "biologio"})

    def test_get_by_field_group_name(self, group_svc) -> None:
        """get_by_field for group_name should work."""
        group_svc.create({"group_name": "fiziko"})
        fetched = group_svc.get_by_field("group_name", "fiziko")
        assert fetched is not None
        assert fetched["group_name"] == "fiziko"


class TestGroupRename:
    """Group rename tests."""

    def test_rename(self, group_svc) -> None:
        """Renaming a group should work."""
        group_svc.create({"group_name": "old_name"})
        updated = group_svc.rename("old_name", "new_name")
        assert updated["group_name"] == "new_name"

        # Old name should no longer exist
        assert group_svc.get_by_field("group_name", "old_name") is None

    def test_rename_nonexistent_raises(self, group_svc) -> None:
        """Renaming a nonexistent group should raise."""
        with pytest.raises(ValueError, match="not found"):
            group_svc.rename("nonexistent", "new")

    def test_rename_to_existing_raises(self, group_svc) -> None:
        """Renaming to an existing name should raise."""
        group_svc.create({"group_name": "a"})
        group_svc.create({"group_name": "b"})
        with pytest.raises(ValueError, match="already exists"):
            group_svc.rename("a", "b")


class TestGroupMembers:
    """Group member management tests."""

    @pytest.fixture(autouse=True)
    def _setup(self, pred_svc, group_svc) -> None:
        """Create predicates and groups for member tests."""
        pred_svc.create({"predicate_id": "wdt:P31", "etikedoj": {"eo": "tipo"}})
        pred_svc.create({"predicate_id": "wdt:P1082", "etikedoj": {"eo": "logxantaro"}})
        group_svc.create({"group_name": "test_group"})

    def test_add_member(self, group_svc) -> None:
        """Adding a member should work."""
        member = group_svc.add_member("test_group", "wdt:P31")
        assert member["predicate_id"] == "wdt:P31"
        assert member["group_uuid"] is not None

    def test_add_duplicate_member_raises(self, group_svc) -> None:
        """Adding a duplicate member should raise."""
        group_svc.add_member("test_group", "wdt:P31")
        with pytest.raises(ValueError, match="already"):
            group_svc.add_member("test_group", "wdt:P31")

    def test_list_members(self, group_svc) -> None:
        """Listing members should return all predicates."""
        group_svc.add_member("test_group", "wdt:P31")
        group_svc.add_member("test_group", "wdt:P1082")
        members = group_svc.list_members("test_group")
        assert len(members) == 2
        pids = [m["predicate_id"] for m in members]
        assert "wdt:P31" in pids
        assert "wdt:P1082" in pids

    def test_remove_member(self, group_svc) -> None:
        """Removing a member should work."""
        group_svc.add_member("test_group", "wdt:P31")
        result = group_svc.remove_member("test_group", "wdt:P31")
        assert result is True
        members = group_svc.list_members("test_group")
        assert len(members) == 0

    def test_remove_nonexistent_member(self, group_svc) -> None:
        """Removing a nonexistent member should return False."""
        result = group_svc.remove_member("test_group", "nonexistent")
        assert result is False

    def test_add_member_to_nonexistent_group(self, group_svc) -> None:
        """Adding to a nonexistent group should raise."""
        with pytest.raises(ValueError, match="not found"):
            group_svc.add_member("nonexistent", "wdt:P31")

    def test_clear_members(self, group_svc) -> None:
        """clear_members should delete all members of a group."""
        group_svc.add_member("test_group", "wdt:P31")
        group_svc.add_member("test_group", "wdt:P1082")
        group = group_svc.get_by_field("group_name", "test_group")
        assert group is not None
        group_svc.clear_members(group["uuid"])
        members = group_svc.list_members("test_group")
        assert len(members) == 0
