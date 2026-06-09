"""Unit tests for the pure unit expression parser (_unit_parser.py).

Tests are pure — no database setup needed.
"""
from __future__ import annotations

import pytest

from A_semantika._unit_parser import (
    ParseError,
    SingularUnit,
    UnitDivision,
    UnitPower,
    UnitProduct,
    normalize,
    parse,
    to_display_string,
)


class TestParse:
    """Test expression parsing."""

    def test_singular_unit(self) -> None:
        """Parse a bare word as a singular unit."""
        result = parse("J")
        assert isinstance(result, SingularUnit)
        assert result.name == "J"

    def test_multi_char_symbol(self) -> None:
        """Parse multi-character symbols like kg."""
        result = parse("kg")
        assert isinstance(result, SingularUnit)
        assert result.name == "kg"

    def test_simple_division(self) -> None:
        """Parse J/K as division."""
        result = parse("J/K")
        assert isinstance(result, UnitDivision)
        assert isinstance(result.numerator, SingularUnit)
        assert result.numerator.name == "J"
        assert isinstance(result.denominator, SingularUnit)
        assert result.denominator.name == "K"

    def test_simple_product(self) -> None:
        """Parse kg*m as product."""
        result = parse("kg*m")
        assert isinstance(result, UnitProduct)
        assert len(result.terms) == 2
        assert result.terms[0].name == "kg"
        assert result.terms[1].name == "m"

    def test_power(self) -> None:
        """Parse m^2 as power."""
        result = parse("m^2")
        assert isinstance(result, UnitPower)
        assert isinstance(result.base, SingularUnit)
        assert result.base.name == "m"
        assert result.exponent == 2

    def test_complex_expression(self) -> None:
        """Parse kg*m/s^2 as complex expression."""
        result = parse("kg*m/s^2")
        assert isinstance(result, UnitDivision)
        # Numerator: kg*m → UnitProduct
        assert isinstance(result.numerator, UnitProduct)
        assert len(result.numerator.terms) == 2
        # Denominator: s^2 → UnitPower
        assert isinstance(result.denominator, UnitPower)
        assert result.denominator.exponent == 2

    def test_parenthesized_denominator(self) -> None:
        """Parse J/(K*kg) with parentheses."""
        result = parse("J/(K*kg)")
        assert isinstance(result, UnitDivision)
        assert isinstance(result.numerator, SingularUnit)
        assert result.numerator.name == "J"
        assert isinstance(result.denominator, UnitProduct)
        assert len(result.denominator.terms) == 2

    def test_power_with_parentheses(self) -> None:
        """Parse (m)^2."""
        result = parse("(m)^2")
        assert isinstance(result, UnitPower)
        assert isinstance(result.base, SingularUnit)
        assert result.base.name == "m"
        assert result.exponent == 2

    def test_chained_division(self) -> None:
        """Parse J/K/s as chained division."""
        result = parse("J/K/s")
        assert isinstance(result, UnitDivision)
        # Should be parsed as (J/K)/s
        assert isinstance(result.numerator, UnitDivision)
        assert isinstance(result.denominator, SingularUnit)
        assert result.denominator.name == "s"

    def test_empty_expression_raises(self) -> None:
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            parse("")

    def test_whitespace_only_raises(self) -> None:
        """Whitespace-only should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            parse("   ")

    def test_invalid_character_raises(self) -> None:
        """Invalid characters should raise ParseError."""
        with pytest.raises(ParseError):
            parse("J@K")

    def test_trailing_content_raises(self) -> None:
        """Trailing content after valid parse should raise ParseError."""
        with pytest.raises(ParseError, match="trailing"):
            parse("J K")

    def test_unclosed_parenthesis_raises(self) -> None:
        """Unclosed parenthesis should raise ParseError."""
        with pytest.raises(ParseError):
            parse("(J/K")

    def test_empty_parenthesis_raises(self) -> None:
        """Empty parentheses should raise ParseError."""
        with pytest.raises(ParseError):
            parse("()")


class TestNormalize:
    """Test AST normalisation."""

    def test_singular_unchanged(self) -> None:
        """SingularUnit should be unchanged by normalisation."""
        expr = SingularUnit("J")
        assert normalize(expr) == expr

    def test_power_unchanged(self) -> None:
        """UnitPower should be unchanged."""
        expr = UnitPower(SingularUnit("m"), 2)
        assert normalize(expr) == expr

    def test_single_term_product_collapsed(self) -> None:
        """UnitProduct with one term should collapse to the term."""
        expr = UnitProduct(terms=(SingularUnit("J"),))
        result = normalize(expr)
        assert isinstance(result, SingularUnit)
        assert result.name == "J"

    def test_product_terms_sorted(self) -> None:
        """Product terms should be sorted alphabetically."""
        expr = UnitProduct(terms=(SingularUnit("kg"), SingularUnit("m")))
        result = normalize(expr)
        assert isinstance(result, UnitProduct)
        assert result.terms[0].name == "kg"
        assert result.terms[1].name == "m"

    def test_nested_product_flattened(self) -> None:
        """Nested UnitProduct should be flattened."""
        inner = UnitProduct(terms=(SingularUnit("K"), SingularUnit("kg")))
        outer = UnitProduct(terms=(SingularUnit("J"), inner))
        result = normalize(outer)
        assert isinstance(result, UnitProduct)
        assert len(result.terms) == 3
        # Sorted: J, K, kg
        assert result.terms[0].name == "J"
        assert result.terms[1].name == "K"
        assert result.terms[2].name == "kg"

    def test_division_with_product_denominator(self) -> None:
        """Division normalises to product with negative powers."""
        expr = UnitDivision(
            SingularUnit("J"),
            UnitProduct(terms=(SingularUnit("K"), SingularUnit("kg"))),
        )
        result = normalize(expr)
        # J/(K*kg) → J * K^-1 * kg^-1
        assert isinstance(result, UnitProduct)
        assert len(result.terms) == 3
        assert result.terms[0] == SingularUnit("J")
        assert isinstance(result.terms[1], UnitPower)
        assert result.terms[1].base.name == "K"
        assert result.terms[1].exponent == -1
        assert isinstance(result.terms[2], UnitPower)
        assert result.terms[2].base.name == "kg"
        assert result.terms[2].exponent == -1


class TestDisplayString:
    """Test AST-to-string conversion."""

    def test_singular(self) -> None:
        assert to_display_string(SingularUnit("J")) == "J"

    def test_division(self) -> None:
        assert to_display_string(UnitDivision(SingularUnit("J"), SingularUnit("K"))) == "J/K"

    def test_product(self) -> None:
        assert to_display_string(UnitProduct(terms=(SingularUnit("kg"), SingularUnit("m")))) == "kg*m"

    def test_power(self) -> None:
        assert to_display_string(UnitPower(SingularUnit("m"), 2)) == "m^2"

    def test_negative_power_standalone(self) -> None:
        """Standalone negative exponent displays as base^-N."""
        assert to_display_string(
            normalize(UnitPower(SingularUnit("K"), -1))
        ) == "K^-1"
        assert to_display_string(
            normalize(UnitPower(SingularUnit("m"), -2))
        ) == "m^-2"

    def test_negative_power_in_product_shows_division(self) -> None:
        """Product with negative exponent displays as division."""
        expr = UnitProduct(terms=(
            SingularUnit("J"),
            UnitPower(SingularUnit("K"), -1),
        ))
        result = to_display_string(normalize(expr))
        assert result == "J/K"

    def test_complex_division_display(self) -> None:
        """Complex division with multiple denominator terms."""
        expr = UnitProduct(terms=(
            SingularUnit("kg"),
            SingularUnit("m"),
            UnitPower(SingularUnit("s"), -2),
        ))
        result = to_display_string(normalize(expr))
        assert result == "kg*m/s^2"

    def test_multi_denominator_parenthesized(self) -> None:
        """Multiple denominator terms get parenthesized."""
        expr = UnitProduct(terms=(
            SingularUnit("J"),
            UnitPower(SingularUnit("K"), -1),
            UnitPower(SingularUnit("kg"), -1),
        ))
        result = to_display_string(normalize(expr))
        assert result == "J/(K*kg)"

    def test_division_with_product_denominator_parenthesized(self) -> None:
        """Division with product denominator adds parentheses."""
        expr = UnitDivision(
            SingularUnit("J"),
            UnitProduct(terms=(SingularUnit("K"), SingularUnit("kg"))),
        )
        assert to_display_string(expr) == "J/(K*kg)"

    def test_parse_roundtrip(self) -> None:
        """parse ∘ to_display_string should roundtrip for normalised forms."""
        expressions = ["J", "K", "J/K", "kg*m", "m^2"]
        for expr_str in expressions:
            ast = parse(expr_str)
            normalised = normalize(ast)
            displayed = to_display_string(normalised)
            # Re-parse and check structural equivalence
            re_parsed = normalize(parse(displayed))
            assert normalised == re_parsed, f"Roundtrip failed for {expr_str!r}: {displayed}"
