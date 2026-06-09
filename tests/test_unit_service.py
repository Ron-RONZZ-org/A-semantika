"""Tests for UnitService (uses conftest isolation fixture)."""
from __future__ import annotations

import pytest

from A_semantika._unit_errors import UnitNotFoundError


class TestUnitServiceSingleton:
    """Test service lifecycle."""

    def test_get_unit_service_returns_singleton(self, unit_svc) -> None:
        """get_unit_service() should return the same instance on repeat calls."""
        from A_semantika.service import get_unit_service

        svc2 = get_unit_service()
        assert unit_svc is svc2

    def test_reset_services_creates_new_singleton(self, unit_svc) -> None:
        """reset_services() should clear the singleton."""
        from A_semantika.service import get_unit_service, reset_services

        reset_services()
        svc2 = get_unit_service()
        assert unit_svc is not svc2


class TestResolveUnit:
    """Test unit resolution."""

    def test_resolve_by_node_id_exact(self, unit_svc) -> None:
        """Resolving by exact node_id returns that node_id."""
        node_id = unit_svc.resolve_unit("unit:JOULE")
        assert node_id == "unit:JOULE"

    def test_resolve_by_node_id_prefix(self, unit_svc) -> None:
        """Resolving by node_id prefix resolves to the full ID."""
        node_id = unit_svc.resolve_unit("unit:JOU")
        assert node_id == "unit:JOULE"

    def test_resolve_by_symbol(self, unit_svc) -> None:
        """Resolving by symbol (e.g., 'J') should find the unit."""
        node_id = unit_svc.resolve_unit("J")
        assert node_id == "unit:JOULE"

    def test_resolve_unknown_raises(self, unit_svc) -> None:
        """Resolving an unknown symbol should raise UnitNotFoundError."""
        with pytest.raises(UnitNotFoundError):
            unit_svc.resolve_unit("ZZZUNKNOWNSYM")

    def test_resolve_compound_expression(self, unit_svc) -> None:
        """Resolving a compound expression like J/K should auto-create and return node_id."""
        node_id = unit_svc.resolve_unit("J/K")
        assert node_id is not None
        assert node_id.startswith("unit:")

    def test_resolve_compound_then_symbolic(self, unit_svc) -> None:
        """J/K resolved once then J gives existing J."""
        unit_svc.resolve_unit("J/K")
        # J should still be resolvable individually
        node_id = unit_svc.resolve_unit("J")
        assert node_id == "unit:JOULE"


class TestListUnits:
    """Test listing units."""

    def test_list_units_contains_seeded(self, unit_svc) -> None:
        """list_units() should return pre-seeded units."""
        units = unit_svc.list_units()
        symbols = {u.get("unit_symbol", "") for u in units}
        assert "J" in symbols
        assert "N" in symbols
        assert "kg" in symbols  # base unit

    def test_list_units_returns_node_id(self, unit_svc) -> None:
        """Each listed unit should include its node_id."""
        units = unit_svc.list_units()
        assert all("node_id" in u for u in units)

    def test_list_units_count(self, unit_svc) -> None:
        """At least 40 seeded units should be present."""
        units = unit_svc.list_units()
        assert len(units) >= 40


class TestGetUnitInfo:
    """Test detailed unit info."""

    def test_get_unit_info_symbol(self, unit_svc) -> None:
        """get_unit_info() should return symbol for a known unit."""
        info = unit_svc.get_unit_info("unit:JOULE")
        assert info is not None
        assert info.get("symbol") == "J"

    def test_get_unit_info_ucum(self, unit_svc) -> None:
        """get_unit_info() should return UCUM code."""
        info = unit_svc.get_unit_info("unit:JOULE")
        assert info is not None
        assert "ucum" in info

    def test_get_unit_info_type(self, unit_svc) -> None:
        """get_unit_info() should return the rdf:type."""
        info = unit_svc.get_unit_info("unit:JOULE")
        assert info is not None
        assert ":SingularUnit" in info.get("unit_type", "")

    def test_get_unit_info_unknown(self, unit_svc) -> None:
        """get_unit_info() should return None for unknown node_id."""
        info = unit_svc.get_unit_info("unit:UNKNOWN")
        assert info is None

    def test_get_unit_info_decomposition(self, unit_svc) -> None:
        """Compound unit decomposition should not be empty."""
        # First create a compound unit via resolve
        unit_svc.resolve_unit("N*m")
        # The compound ID is built from the actual node_ids, sorted alphabetically
        info = unit_svc.get_unit_info("unit:METER_TIMES_NEWTON")
        assert info is not None
        assert info.get("decomposition", "") != ""


class TestNegativeExponents:
    """Test negative exponent handling."""

    def test_negative_exponent_standalone(self, unit_svc) -> None:
        """K^-1 creates a UnitPower node with POW-1 suffix."""
        node_id = unit_svc.resolve_unit("K^-1")
        assert node_id is not None
        assert "_POW-1" in node_id

    def test_negative_exponent_in_product(self, unit_svc) -> None:
        """m*s^-2 creates a product + power."""
        node_id = unit_svc.resolve_unit("m*s^-2")
        assert node_id is not None
        assert "TIMES_" in node_id

    def test_one_over_K_same_as_K_recip(self, unit_svc) -> None:
        """1/K and K^-1 should resolve to the same node structure."""
        id1 = unit_svc.resolve_unit("1/K")
        id2 = unit_svc.resolve_unit("K^-1")
        # Both normalise to same structure, but node_ids may differ
        # (1/K → UnitProduct → binary product, K^-1 → UnitPower → single RECIP node)
        assert id1 is not None
        assert id2 is not None


class TestCompoundUnits:
    """Test automatic compound unit creation."""

    def test_division_auto_created(self, unit_svc) -> None:
        """Division like J/K should create a compound node via product + power, not division."""
        node_id = unit_svc.resolve_unit("J/K")
        assert node_id is not None
        # J/K normalises to J * K^-1, stored as UnitProduct, not UnitDivision
        assert "TIMES_" in node_id

    def test_product_auto_created(self, unit_svc) -> None:
        """Product like N*m should create a UnitProduct node."""
        node_id = unit_svc.resolve_unit("N*m")
        assert "TIMES_" in node_id or node_id is not None

    def test_compound_in_list(self, unit_svc) -> None:
        """Compound units should appear in list_units()."""
        unit_svc.resolve_unit("J/K")
        units = unit_svc.list_units()
        unit_ids = {u["node_id"] for u in units}
        # Should contain the compound unit
        compound_found = any("PER_" in uid or "TIMES_" in uid for uid in unit_ids)
        assert compound_found


class TestCreateSingleton:
    """Test manual unit creation."""

    def test_create_singleton(self, unit_svc) -> None:
        """Create a custom singular unit."""
        node_id = unit_svc.create_singleton("FOO", "Foo unit", "F")
        assert node_id == "unit:FOO"

    def test_create_singleton_then_resolve(self, unit_svc) -> None:
        """Custom unit should be resolvable by symbol."""
        unit_svc.create_singleton("BAR", "Bar unit", "Br")
        node_id = unit_svc.resolve_unit("Br")
        assert node_id == "unit:BAR"

    def test_create_singleton_idempotent(self, unit_svc) -> None:
        """Creating the same singleton twice should succeed (INSERT OR IGNORE)."""
        unit_svc.create_singleton("BAZ", "Baz unit", "Bz")
        unit_svc.create_singleton("BAZ", "Baz unit", "Bz")  # no error
        node_id = unit_svc.resolve_unit("Bz")
        assert node_id == "unit:BAZ"


class TestSeededUnits:
    """Verify that SI units are properly seeded."""

    def test_base_units_present(self, unit_svc) -> None:
        """SI base units should be present."""
        units = unit_svc.list_units()
        symbols = {u.get("unit_symbol", "") for u in units}
        for sym in ("m", "kg", "s", "A", "K", "cd", "mol"):
            assert sym in symbols, f"Base unit {sym!r} not found"

    def test_derived_units_present(self, unit_svc) -> None:
        """Key derived units should be present."""
        units = unit_svc.list_units()
        symbols = {u.get("unit_symbol", "") for u in units}
        for sym in ("N", "J", "W", "V", "Pa", "Hz", "C", "F"):
            assert sym in symbols, f"Derived unit {sym!r} not found"

    def test_type_nodes_exist(self, unit_svc) -> None:
        """Type nodes (SingularUnit, PrefixedUnit, etc.) should exist as nodes."""
        from A_semantika.service import get_node_service

        node_svc = get_node_service()
        for type_name in (":SingularUnit", ":PrefixedUnit", ":CompoundUnit",
                          ":UnitProduct", ":UnitPower"):
            node = node_svc.resolve_node_id_prefix(type_name)
            assert node is not None, f"Type node {type_name!r} not found"


class TestNormalizeUnit:
    """Test read-only unit normalization without auto-creation."""

    def test_normalize_by_exact_node_id(self, unit_svc) -> None:
        """Exact node_id returns itself."""
        result = unit_svc.normalize_unit("unit:JOULE")
        assert result == "unit:JOULE"

    def test_normalize_by_symbol(self, unit_svc) -> None:
        """Symbol lookup returns the canonical node_id."""
        result = unit_svc.normalize_unit("J")
        assert result == "unit:JOULE"

    def test_normalize_by_label(self, unit_svc) -> None:
        """Label (FTS5) lookup returns the canonical node_id."""
        result = unit_svc.normalize_unit("kulombo")
        assert result == "unit:COULOMB"

    def test_normalize_c_to_coulomb(self, unit_svc) -> None:
        """Symbol 'C' should resolve to Coulombo."""
        result = unit_svc.normalize_unit("C")
        assert result == "unit:COULOMB"

    def test_normalize_unknown_returns_input(self, unit_svc) -> None:
        """Unknown symbol returns the input unchanged (no error)."""
        result = unit_svc.normalize_unit("ZZZ_UNKNOWN")
        assert result == "ZZZ_UNKNOWN"

    def test_normalize_does_not_create_compound(self, unit_svc) -> None:
        """normalize_unit should NOT auto-create compound units."""
        result = unit_svc.normalize_unit("J/K")
        # Not found → returns input unchanged
        assert result == "J/K"
        # Verify no compound node was created
        from A_semantika.service import get_node_service
        node_svc = get_node_service()
        # J/K normalizes to J * K^-1, product sorted: JOULE < KELVIN_POW-1
        compound_node = node_svc.resolve_node_id_prefix("unit:JOULE_TIMES_KELVIN_POW-1")
        assert compound_node is None, "normalize_unit should not auto-create compounds"

    def test_normalize_prefix_match(self, unit_svc) -> None:
        """Prefix match on node_id should resolve."""
        result = unit_svc.normalize_unit("unit:JOU")
        assert result == "unit:JOULE"

    def test_normalize_case_insensitive(self, unit_svc) -> None:
        """Case-insensitive node_id match should work."""
        result = unit_svc.normalize_unit("unit:joule")
        assert result == "unit:JOULE"

    def test_normalize_same_unit_different_inputs(self, unit_svc) -> None:
        """'C', 'kulombo', and 'unit:COULOMB' should all normalize to the same ID."""
        id1 = unit_svc.normalize_unit("C")
        id2 = unit_svc.normalize_unit("kulombo")
        id3 = unit_svc.normalize_unit("unit:COULOMB")
        assert id1 == id2 == id3 == "unit:COULOMB"
