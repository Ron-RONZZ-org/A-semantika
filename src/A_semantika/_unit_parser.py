"""Pure expression parser for unit expressions.

Grammar::

    expression  → product ("/" product)*
    product     → factor ("*" factor)*
    factor      → WORD ("^" INTEGER)? | INTEGER | "(" expression ")"

The parser produces ``UnitDivision`` nodes for ``/`` syntax, but
``normalize()`` converts them to the canonical product-of-powers form
(``a/b → a * b^-1``).

Examples (raw parse):
    ``"J"``       → ``SingularUnit("J")``
    ``"J/K"``     → ``UnitDivision(SingularUnit("J"), SingularUnit("K"))``
    ``"m^2"``     → ``UnitPower(SingularUnit("m"), 2)``
    ``"K^-1"``    → ``UnitPower(SingularUnit("K"), -1)``

Examples (normalised — service layer always normalises):
    ``"J/K"``     → ``UnitProduct([J, UnitPower(K, -1)])``
    ``"m/s^2"``   → ``UnitProduct([m, UnitPower(s, -2)])``

All functions are pure — no DB access, no side effects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar


# ── AST node types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class UnitExpression:
    """Base class for unit expression AST nodes."""
    pass


@dataclass(frozen=True)
class SingularUnit(UnitExpression):
    """A named unit (e.g. meter, joule, kelvin).

    The *name* is the WORD token from the expression (e.g. ``"J"``, ``"kg"``).
    It will be resolved to a node_id by the service layer.
    """
    name: str


@dataclass(frozen=True)
class UnitPower(UnitExpression):
    """A unit raised to an integer power.

    ``m^2`` → base=m, exponent=2
    """
    base: UnitExpression
    exponent: int


@dataclass(frozen=True)
class UnitProduct(UnitExpression):
    """Product of two or more units (flattened, sorted)."""
    terms: tuple[UnitExpression, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class UnitDivision(UnitExpression):
    """Division of numerator by denominator."""
    numerator: UnitExpression
    denominator: UnitExpression


# ── Lexer tokens ────────────────────────────────────────────────────────

_TOKEN_PATTERN = re.compile(r"""
    (?P<WORD>[a-zA-Z_][a-zA-Z0-9_]*)   |
    (?P<INTEGER>-?\d+)                   |
    (?P<STAR>\*)                         |
    (?P<SLASH>/)                         |
    (?P<CARET>\^)                        |
    (?P<LPAREN>\()                       |
    (?P<RPAREN>\))                       |
    (?P<WS>\s+)                          |
    (?P<ERROR>.+?)
""", re.VERBOSE)


class ParseError(ValueError):
    """Raised when a unit expression cannot be parsed."""
    pass


def _tokenize(expr: str) -> list[tuple[str, str]]:
    """Tokenize a unit expression string.

    Returns:
        List of ``(token_type, token_value)`` pairs.

    Raises:
        ParseError: If an unrecognised character is found.
    """
    tokens: list[tuple[str, str]] = []
    for m in _TOKEN_PATTERN.finditer(expr):
        kind = m.lastgroup
        assert kind is not None
        if kind == "WS":
            continue
        if kind == "ERROR":
            raise ParseError(
                f"Unrecognised character {m.group()!r} in unit expression "
                f"at position {m.start()}"
            )
        tokens.append((kind, m.group()))
    return tokens


# ── Parser ──────────────────────────────────────────────────────────────


class _Parser:
    """Recursive-descent parser for unit expressions."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        """Return the current token without consuming it."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected_kind: str | None = None) -> tuple[str, str]:
        """Consume and return the current token.

        Args:
            expected_kind: If given, raise ParseError if token kind mismatches.

        Returns:
            The consumed ``(kind, value)`` pair.
        """
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of expression")
        if expected_kind is not None and tok[0] != expected_kind:
            raise ParseError(
                f"Expected {expected_kind!r} but got {tok[0]!r} ({tok[1]!r})"
            )
        self.pos += 1
        return tok

    def parse(self) -> UnitExpression:
        """Parse a complete unit expression.

        ``expression → product ("/" product)*``
        """
        left = self._parse_product()
        while self.peek() is not None and self.peek()[0] == "SLASH":
            self.consume("SLASH")
            right = self._parse_product()
            left = UnitDivision(numerator=left, denominator=right)
        return left

    def _parse_product(self) -> UnitExpression:
        """``product → factor ("*" factor)*``

        Single factor returns the factor directly (no wrapping).
        Multiple factors return a ``UnitProduct`` with flattened, sorted terms.
        """
        factors: list[UnitExpression] = [self._parse_factor()]
        while self.peek() is not None and self.peek()[0] == "STAR":
            self.consume("STAR")
            factors.append(self._parse_factor())
        if len(factors) == 1:
            return factors[0]
        return UnitProduct(terms=_flatten_and_sort(factors))

    def _parse_factor(self) -> UnitExpression:
        """``factor → WORD ("^" INTEGER)? | INTEGER | "(" expression ")"``"""
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of expression")

        if tok[0] == "WORD":
            self.consume("WORD")
            name = tok[1]
            exponent = self._parse_exponent()
            if exponent is not None:
                return UnitPower(SingularUnit(name), exponent)
            return SingularUnit(name)

        if tok[0] == "INTEGER":
            self.consume("INTEGER")
            name = tok[1]
            exponent = self._parse_exponent()
            if exponent is not None:
                return UnitPower(SingularUnit(name), exponent)
            return SingularUnit(name)

        if tok[0] == "LPAREN":
            self.consume("LPAREN")
            inner = self.parse()
            self.consume("RPAREN")
            exponent = self._parse_exponent()
            if exponent is not None:
                return UnitPower(inner, exponent)
            return inner

        raise ParseError(
            f"Unexpected token {tok[0]!r} ({tok[1]!r}) — expected WORD or '('"
        )

    def _parse_exponent(self) -> int | None:
        """Optional ``"^" INTEGER`` suffix.

        Returns the exponent integer, or ``None`` if no caret follows.
        """
        if self.peek() is not None and self.peek()[0] == "CARET":
            self.consume("CARET")
            tok = self.consume("INTEGER")
            return int(tok[1])
        return None


# ── Normalisation helpers ───────────────────────────────────────────────


def _sort_key(expr: UnitExpression) -> tuple:
    """Generate a sort key for a unit expression.

    Used for canonical ordering of product terms.
    """
    if isinstance(expr, SingularUnit):
        return (0, expr.name.lower())
    if isinstance(expr, UnitPower):
        return (1, _sort_key(expr.base), expr.exponent)
    if isinstance(expr, UnitProduct):
        return (2, tuple(_sort_key(t) for t in expr.terms))
    if isinstance(expr, UnitDivision):
        return (3, _sort_key(expr.numerator), _sort_key(expr.denominator))
    return (99,)


def _invert_power(expr: UnitExpression) -> UnitExpression:
    """Invert a unit expression: ``a → a^-1``, ``a^n → a^-n``."""
    if isinstance(expr, UnitPower):
        if expr.exponent == -1:
            return expr.base  # a^-1 inverted → a
        return UnitPower(base=expr.base, exponent=-expr.exponent)
    return UnitPower(base=expr, exponent=-1)


def _flatten_and_sort(factors: list[UnitExpression]) -> tuple[UnitExpression, ...]:
    """Flatten nested products and sort factors into canonical order.

    ``UnitProduct([a, UnitProduct([b, c])])`` → ``(a, b, c)`` (flattened)
    ``UnitProduct([b, a])`` → ``(a, b)`` (sorted)
    """
    flat: list[UnitExpression] = []
    for f in factors:
        if isinstance(f, UnitProduct):
            flat.extend(f.terms)
        else:
            flat.append(f)
    flat.sort(key=_sort_key)
    return tuple(flat)


# ── Public API ──────────────────────────────────────────────────────────


def parse(expr: str) -> UnitExpression:
    """Parse a unit expression string into an AST.

    Args:
        expr: Unit expression string, e.g. ``"J/K"``, ``"kg*m/s^2"``.

    Returns:
        ``UnitExpression`` AST node.

    Raises:
        ParseError: If the expression cannot be parsed.
        ValueError: If the expression is empty.
    """
    stripped = expr.strip()
    if not stripped:
        raise ValueError("Cannot parse empty unit expression")
    tokens = _tokenize(stripped)
    if not tokens:
        raise ValueError("Cannot parse empty unit expression")
    parser = _Parser(tokens)
    result = parser.parse()
    # Ensure all tokens were consumed
    if parser.peek() is not None:
        remaining = " ".join(t[1] for t in parser.tokens[parser.pos:])
        raise ParseError(f"Unexpected trailing content: {remaining!r}")
    return result


def normalize(expr: UnitExpression) -> UnitExpression:
    """Return a canonical (normalised) form of a unit expression.

    Flattens nested products, sorts terms alphabetically,
    simplifies trivial expressions, and converts ``UnitDivision``
    to the uniform product-of-powers form (``a/b → a * b^-1``).

    The normalised form is suitable for structural deduplication:
    two expressions that are semantically equivalent (e.g. ``J/K``
    and ``J*K^-1``) produce the same normalised AST.
    """
    if isinstance(expr, SingularUnit):
        return expr
    if isinstance(expr, UnitPower):
        return UnitPower(base=normalize(expr.base), exponent=expr.exponent)
    if isinstance(expr, UnitProduct):
        terms = _flatten_and_sort([normalize(t) for t in expr.terms])
        # Filter out dimensionless "1" terms (e.g. from normalising "1/K")
        filtered = [t for t in terms
                    if not (isinstance(t, SingularUnit) and t.name == "1")]
        if not filtered:
            return SingularUnit("1")
        if len(filtered) == 1:
            return filtered[0]
        return UnitProduct(terms=filtered)
    if isinstance(expr, UnitDivision):
        # Normalise a/b to a * b^-1 — uniform product-of-powers model.
        # Distribute the -1 exponent across all denominator terms.
        num = normalize(expr.numerator)
        den = normalize(expr.denominator)

        # Numerator terms
        num_terms = list(num.terms) if isinstance(num, UnitProduct) else [num]

        # Denominator terms with inverted exponents
        den_raw = list(den.terms) if isinstance(den, UnitProduct) else [den]
        den_inv = [_invert_power(t) for t in den_raw]

        all_terms = _flatten_and_sort(num_terms + den_inv)
        # Filter out dimensionless "1" (e.g. from normalising "1/K")
        filtered = [t for t in all_terms
                    if not (isinstance(t, SingularUnit) and t.name == "1")]
        if not filtered:
            return SingularUnit("1")
        if len(filtered) == 1:
            return filtered[0]
        return UnitProduct(terms=filtered)
    return expr


def to_display_string(expr: UnitExpression) -> str:
    """Convert a normalised unit expression to a human-readable string.

    Handles negative exponents by rendering them as division
    (``a*b^-1 → "a/b"``) for readability.
    """
    if isinstance(expr, SingularUnit):
        return expr.name
    if isinstance(expr, UnitPower):
        base = to_display_string(expr.base)
        if expr.exponent == 1:
            return base
        return f"{base}^{expr.exponent}"
    if isinstance(expr, UnitProduct):
        # Split terms into numerator (non-negative exp) and denominator (negative exp)
        num_parts: list[str] = []
        den_parts: list[str] = []
        for t in expr.terms:
            if isinstance(t, UnitPower) and t.exponent < 0:
                # Invert for display: K^-1 → K^1 → "K"
                inv = UnitPower(base=t.base, exponent=-t.exponent)
                den_parts.append(to_display_string(inv))
            else:
                num_parts.append(to_display_string(t))
        if not den_parts:
            return "*".join(num_parts)
        num_str = "*".join(num_parts) if num_parts else "1"
        den_str = "*".join(den_parts)
        if len(den_parts) > 1:
            den_str = f"({den_str})"
        return f"{num_str}/{den_str}"
    if isinstance(expr, UnitDivision):
        # Fallback for un-normalised ASTs — normalise first for the canonical path
        return to_display_string(normalize(expr))
    return ""
