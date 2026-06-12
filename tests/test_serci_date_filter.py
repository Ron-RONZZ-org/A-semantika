"""Tests for serci --dato-de / --dato-gis date filtering.

Notes:
- storage.py init_db() seeds 6 default unit nodes with ``tipo`` triples
  at today's timestamp — these appear in unfiltered queries as well.
- Our test creates 3 additional triples at controlled past dates.
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app

# Number of seed triples created by init_db() (6 unit nodes × 1 tipo each)
_SEED_TRIPLES = 6


@pytest.fixture(autouse=True)
def _setup(node_svc, pred_svc, triple_svc, monkeypatch) -> None:
    """Create nodes, predicates, and triples at controlled timestamps."""
    node_svc.create({"node_id": "N_ALPHA", "etikedoj": {"eo": "Alfa"}})
    node_svc.create({"node_id": "N_BRAVO", "etikedoj": {"eo": "Bravo"}})
    node_svc.create({"node_id": "N_CHARLIE", "etikedoj": {"eo": "Charlie"}})
    pred_svc.create({"predicate_id": "rilatas_al", "etikedoj": {"eo": "rilatas al"}})

    import A_semantika._triple_service as ts_mod

    # Triple 1 — old date (2026-01-15)
    monkeypatch.setattr(ts_mod, "now", lambda: "2026-01-15T10:00:00+00:00")
    triple_svc.add(
        subject_uuid="N_ALPHA", predicate_id="rilatas_al",
        object_value="N_BRAVO", object_type="uri",
    )

    # Triple 2 — middle date (2026-04-20)
    monkeypatch.setattr(ts_mod, "now", lambda: "2026-04-20T12:30:00+00:00")
    triple_svc.add(
        subject_uuid="N_BRAVO", predicate_id="rilatas_al",
        object_value="N_CHARLIE", object_type="uri",
    )

    # Triple 3 — recent date (2026-06-10)
    monkeypatch.setattr(ts_mod, "now", lambda: "2026-06-10T08:15:00+00:00")
    triple_svc.add(
        subject_uuid="N_ALPHA", predicate_id="rilatas_al",
        object_value="N_CHARLIE", object_type="uri",
    )


runner = CliRunner()


class TestSerciDateFilter:
    """CLI tests: serci with --dato-de / --dato-gis."""

    def test_no_date_filters_returns_all(self):
        """serci without date filters should return all triples."""
        result = runner.invoke(app, ["serci"])
        assert result.exit_code == 0
        total = _SEED_TRIPLES + 3
        assert f"{total} arkoj" in result.stdout

    @pytest.mark.parametrize("flag", ["--dato-de", "--from"])
    def test_dato_de_filters_old(self, flag):
        """--dato-de 20260401 should exclude the Jan triple (before April)."""
        result = runner.invoke(app, ["serci", flag, "20260401"])
        assert result.exit_code == 0
        # 6 seed + Apr + Jun = 8
        assert "8 arkoj" in result.stdout

    def test_dato_gis_filters_recent(self):
        """--dato-gis 20260501 should exclude the June triple + seed (after May)."""
        result = runner.invoke(app, ["serci", "--dato-gis", "20260501"])
        assert result.exit_code == 0
        # Seed triples (today = June 12) and Jun triple are after May 1,
        # leaving only Jan + Apr = 2
        assert "2 arkoj" in result.stdout

    def test_dato_de_and_gis_middle_range(self):
        """Both bounds should return only Apr triple (excludes Jan, seed, Jun)."""
        result = runner.invoke(app, ["serci", "--dato-de", "20260401", "--dato-gis", "20260501"])
        assert result.exit_code == 0
        # Only Apr 20 triple is within Apr 1 - May 1 range
        assert "1 arko" in result.stdout

    def test_no_matches_outside_range(self):
        """Date range outside all triples should return empty."""
        result = runner.invoke(app, ["serci", "--dato-de", "20240101", "--dato-gis", "20240102"])
        assert result.exit_code == 0
        assert "Neniuj arkoj" in result.stdout

    def test_invalid_date_raises_error(self):
        """Completely invalid date (month 99) should show an error."""
        result = runner.invoke(app, ["serci", "--dato-de", "99"])
        assert result.exit_code == 1
        assert "Nevalida dato" in result.stdout or "Invalid date" in result.stdout

    def test_dato_de_with_positional_search_term(self):
        """--dato-de with positional search term should filter by date."""
        result = runner.invoke(app, ["serci", "Alfa", "--dato-de", "20260401"])
        assert result.exit_code == 0
        # After April 2026, only the June triple (Alfa -> Charlie) matches "Alfa"
        assert "1 arko" in result.stdout

    def test_dato_de_with_explicit_flag(self):
        """--dato-de with --subjekto flag should filter by date."""
        result = runner.invoke(app, ["serci", "--subjekto", "Bravo", "--dato-de", "20260301"])
        assert result.exit_code == 0
        # Bravo is subject only in the Apr triple, which is after Mar
        assert "1 arko" in result.stdout


class TestTripleServiceSearchDateFilter:
    """Unit tests: TripleService.search_triples() with date bounds."""

    def test_search_with_dato_de(self, triple_svc):
        """search_triples with dato_de should filter older triples."""
        from A_semantika._triple_search import search_triples_any_field
        from A_semantika.service import get_node_service, get_predicate_service

        node_svc = get_node_service()
        pred_svc = get_predicate_service()
        results = search_triples_any_field(
            triple_svc, node_svc, pred_svc, "Alfa",
            dato_de="2026-04-01T00:00:00+00:00",
        )
        assert len(results) == 1  # only the June triple

    def test_search_with_dato_gis(self, triple_svc):
        """search_triples with dato_gis should filter newer triples."""
        from A_semantika._triple_search import search_triples_any_field
        from A_semantika.service import get_node_service, get_predicate_service

        node_svc = get_node_service()
        pred_svc = get_predicate_service()
        results = search_triples_any_field(
            triple_svc, node_svc, pred_svc, "Alfa",
            dato_gis="2026-03-01T00:00:00+00:00",
        )
        assert len(results) == 1  # only the January triple

    def test_search_with_both_bounds(self, triple_svc):
        """search_triples with both bounds returns January triple."""
        from A_semantika._triple_search import search_triples_any_field
        from A_semantika.service import get_node_service, get_predicate_service

        node_svc = get_node_service()
        pred_svc = get_predicate_service()
        results = search_triples_any_field(
            triple_svc, node_svc, pred_svc, "Alfa",
            dato_de="2026-01-01T00:00:00+00:00",
            dato_gis="2026-02-01T00:00:00+00:00",
        )
        assert len(results) == 1  # only the January triple

    def test_search_empty_range(self, triple_svc):
        """search_triples with non-overlapping bounds returns empty."""
        from A_semantika._triple_search import search_triples_any_field
        from A_semantika.service import get_node_service, get_predicate_service

        node_svc = get_node_service()
        pred_svc = get_predicate_service()
        results = search_triples_any_field(
            triple_svc, node_svc, pred_svc, "Alfa",
            dato_de="2027-01-01T00:00:00+00:00",
        )
        assert len(results) == 0

    def test_search_by_labels_with_date(self, triple_svc):
        """search_triples_by_labels with date bounds filters correctly."""
        from A_semantika._triple_search import search_triples_by_labels
        from A_semantika.service import get_node_service, get_predicate_service

        node_svc = get_node_service()
        pred_svc = get_predicate_service()
        results = search_triples_by_labels(
            triple_svc, node_svc, pred_svc,
            subject="Alfa",
            dato_de="2026-04-01T00:00:00+00:00",
        )
        assert len(results) == 1  # June triple only

    def test_no_filters_raw_query_with_date(self, triple_svc):
        """search_triples without search terms but with date bounds works."""
        results = triple_svc.search_triples("1=1", [], dato_de="2026-04-01T00:00:00+00:00")
        # 6 seed (today) + Apr + Jun = 8
        assert len(results) == _SEED_TRIPLES + 2
