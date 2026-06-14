"""Test configuration for A-semantika.

Autouse fixture isolates all database operations to a temp directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from typer.testing import CliRunner

from A_semantika.service import reset_services


@pytest.fixture(autouse=True)
def isolate_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[None, None, None]:
    """Isolate all database operations to a temp directory.

    This fixture:
    1. Monkeypatches the data_dir to tmp_path
    2. Resets all service singletons
    3. Closes any existing DB connection
    """
    from A_semantika import data as data_module

    monkeypatch.setattr(data_module.storage, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(data_module.storage, "_db_instance", None)
    reset_services()

    yield

    # Cleanup after test
    from A_semantika.data.storage import close_db

    close_db()
    reset_services()


@pytest.fixture
def runner() -> CliRunner:
    """Return a CliRunner for CLI tests."""
    return CliRunner()


@pytest.fixture
def db():
    """Return an initialized database for direct testing."""
    from A_semantika.data.storage import get_db

    reset_services()
    return get_db()


@pytest.fixture
def node_svc():
    """Return a NodeService instance."""
    from A_semantika.service import get_node_service

    reset_services()
    return get_node_service()


@pytest.fixture
def pred_svc():
    """Return a PredicateService instance."""
    from A_semantika.service import get_predicate_service

    reset_services()
    return get_predicate_service()


@pytest.fixture
def group_svc():
    """Return a PredicateGroupService instance."""
    from A_semantika.service import get_predicate_group_service

    reset_services()
    return get_predicate_group_service()


@pytest.fixture
def triple_svc():
    """Return a TripleService instance."""
    from A_semantika.service import get_triple_service

    reset_services()
    return get_triple_service()


@pytest.fixture
def unit_svc():
    """Return a UnitService instance."""
    from A_semantika.service import get_unit_service

    reset_services()
    return get_unit_service()
