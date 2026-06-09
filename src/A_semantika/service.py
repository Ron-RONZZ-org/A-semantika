"""A-semantika service layer — import hub with singleton accessors.

All service singletons are lazily initialized on first access.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_group_service import PredicateGroupService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService
    from A_semantika._unit_service import UnitService


# Singleton holders
_node_service: NodeService | None = None
_predicate_service: PredicateService | None = None
_predicate_group_service: PredicateGroupService | None = None
_triple_service: TripleService | None = None
_unit_service: UnitService | None = None


def get_node_service() -> "NodeService":
    """Return the singleton NodeService."""
    global _node_service
    if _node_service is None:
        from A_semantika._node_service import NodeService
        from A_semantika.data.storage import get_db

        _node_service = NodeService(get_db())
    return _node_service


def get_predicate_service() -> "PredicateService":
    """Return the singleton PredicateService."""
    global _predicate_service
    if _predicate_service is None:
        from A_semantika._predicate_service import PredicateService
        from A_semantika.data.storage import get_db

        _predicate_service = PredicateService(get_db())
    return _predicate_service


def get_predicate_group_service() -> "PredicateGroupService":
    """Return the singleton PredicateGroupService."""
    global _predicate_group_service
    if _predicate_group_service is None:
        from A_semantika._predicate_group_service import PredicateGroupService
        from A_semantika.data.storage import get_db

        _predicate_group_service = PredicateGroupService(get_db())
    return _predicate_group_service


def get_triple_service() -> "TripleService":
    """Return the singleton TripleService."""
    global _triple_service
    if _triple_service is None:
        from A_semantika._triple_service import TripleService
        from A_semantika.data.storage import get_db

        _triple_service = TripleService(get_db())
    return _triple_service


def get_unit_service() -> "UnitService":
    """Return the singleton UnitService."""
    global _unit_service
    if _unit_service is None:
        from A_semantika._unit_service import UnitService
        from A_semantika.data.storage import get_db

        _unit_service = UnitService(
            db=get_db(),
            node_svc=get_node_service(),
            triple_svc=get_triple_service(),
        )
    return _unit_service


def reset_services() -> None:
    """Reset all service singletons (used in tests)."""
    global _node_service, _predicate_service, _predicate_group_service, _triple_service, _unit_service
    _node_service = None
    _predicate_service = None
    _predicate_group_service = None
    _triple_service = None
    _unit_service = None
