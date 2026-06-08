"""UnitService — facade for unit ontology operations.

Provides unit node creation, expression-based auto-creation,
decomposition, and the core ``resolve_unit()`` chain used by CLI ``-u`` flags.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from A_semantika._unit_parser import (
    UnitDivision,
    UnitExpression,
    UnitPower,
    UnitProduct,
    SingularUnit,
    normalize,
    parse,
    to_display_string,
)
from A_semantika._unit_seed_data import ALL_UNITS, BASE_AND_DERIVED, SI_BASE_UNITS
from A_semantika.data.storage import now

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService
    from A.data.base import SQLiteDB


class UnitNotFoundError(ValueError):
    """Raised when a unit name or expression cannot be found or created."""
    pass


class UnitService:
    """Facade for unit ontology operations.

    Wraps NodeService and TripleService to provide unit-specific
    create, resolve, and decompose operations.
    """

    def __init__(
        self,
        db: SQLiteDB,
        node_svc: NodeService,
        triple_svc: TripleService,
    ) -> None:
        self.db = db
        self.node_svc = node_svc
        self.triple_svc = triple_svc
        self._base_units_ensured: bool = False

    # ── Lazy seeding ─────────────────────────────────────────────────

    def _ensure_base_units(self) -> None:
        """Seed SI base units, derived units, and prefixes on first use.

        Uses INSERT OR IGNORE so repeated calls are no-ops.
        Called lazily — not at import time or init_db() time.
        """
        if self._base_units_ensured:
            return

        now_iso = now()
        for unit in BASE_AND_DERIVED:
            self._insert_unit_node(unit, now_iso)
        for prefix in SI_BASE_UNITS:
            # Prefixes are nodes themselves, no special seeding needed yet
            pass
        for prefix_data in ALL_UNITS[len(BASE_AND_DERIVED):]:
            self._insert_unit_node(prefix_data, now_iso)
        self._base_units_ensured = True

    def _insert_unit_node(self, unit: dict, now_iso: str) -> None:
        """Insert a unit node with its type, symbol, and UCUM triples."""
        etikedoj = json.dumps(unit["etikedoj"])
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (unit["node_id"], etikedoj, now_iso, now_iso),
        )
        # rdf:type: base units and derived units are SingularUnit
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, 'rdf:type', ':SingularUnit', 'uri', ?)",
            (unit["node_id"], now_iso),
        )
        # :symbol triple
        symbol = unit.get("symbol")
        if symbol:
            self.db.execute(
                "INSERT OR IGNORE INTO triples "
                "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
                "VALUES (?, ':symbol', ?, 'literal', ?)",
                (unit["node_id"], symbol, now_iso),
            )
        # :ucumCode triple
        ucum = unit.get("ucum")
        if ucum:
            self.db.execute(
                "INSERT OR IGNORE INTO triples "
                "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
                "VALUES (?, ':ucumCode', ?, 'literal', ?)",
                (unit["node_id"], ucum, now_iso),
            )
        # :multiplier triple (for derived units with conversion)
        mult = unit.get("multiplier")
        if mult is not None:
            self.db.execute(
                "INSERT OR IGNORE INTO triples "
                "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
                "VALUES (?, ':multiplier', ?, 'literal', ?)",
                (unit["node_id"], str(mult), now_iso),
                # object_unit is None because multiplier is dimensionless
            )
        # :offset triple (for units like Celsius)
        offset = unit.get("offset")
        if offset is not None:
            self.db.execute(
                "INSERT OR IGNORE INTO triples "
                "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
                "VALUES (?, ':offset', ?, 'literal', ?)",
                (unit["node_id"], str(offset), now_iso),
            )

    def _ensure_unit_initialised(self) -> None:
        """Ensure base units are seeded before any unit operation."""
        self._ensure_base_units()

    # ── Symbol / name resolution ─────────────────────────────────────

    def _find_unit_by_symbol(self, name: str) -> dict | None:
        """Find a unit node whose ``:symbol`` triple matches *name*.

        Tries exact match first, then case-insensitive.
        """
        # Exact :symbol match
        row = self.db.execute_one(
            "SELECT n.* FROM nodes n "
            "JOIN triples t ON t.subject_uuid = n.node_id "
            "WHERE t.predicate_id = ':symbol' AND t.object_value = ? "
            "AND t.object_type = 'literal'",
            (name,),
        )
        if row:
            return row
        # Case-insensitive fallback
        rows = self.db.execute(
            "SELECT n.* FROM nodes n "
            "JOIN triples t ON t.subject_uuid = n.node_id "
            "WHERE t.predicate_id = ':symbol' AND t.object_value LIKE ? "
            "AND t.object_type = 'literal'",
            (name,),
        )
        if len(rows) == 1:
            return rows[0]
        return None

    def _resolve_word_to_node(self, word: str) -> dict:
        """Resolve a WORD token from the expression parser to a unit node.

        Resolution chain:
          1. Try as an exact ``node_id`` match
          2. Try as a ``:symbol`` triple value
          3. Try as a label / FTS5 search
        """
        # Phase 1: exact node_id
        node = self.node_svc.resolve_node_id_prefix(word)
        if node:
            return node

        # Phase 2: symbol lookup
        node = self._find_unit_by_symbol(word)
        if node:
            return node

        # Phase 3: FTS5 label search
        results = self.node_svc.search(word, limit=2)
        if len(results) == 1:
            return results[0]

        raise UnitNotFoundError(
            f"Unit not found: {word!r}. "
            f"Create it first with 'A semantika unuo aldoni {word}' "
            f"or use an existing unit ID."
        )

    # ── Compound unit creation from AST ───────────────────────────────

    def _create_from_ast(self, expr: UnitExpression) -> str:
        """Walk an AST and create missing compound unit nodes.

        Returns the ``node_id`` of the root unit.
        """
        expr = normalize(expr)

        if isinstance(expr, SingularUnit):
            node = self._resolve_word_to_node(expr.name)
            return node["node_id"]

        if isinstance(expr, UnitPower):
            base_id = self._create_from_ast(expr.base)
            return self._build_power_node(base_id, expr.exponent)

        if isinstance(expr, UnitProduct):
            term_ids = []
            for term in expr.terms:
                term_id = self._create_from_ast(term)
                term_ids.append(term_id)
            return self._build_product_node(term_ids)

        if isinstance(expr, UnitDivision):
            num_id = self._create_from_ast(expr.numerator)
            den_id = self._create_from_ast(expr.denominator)
            return self._build_division_node(num_id, den_id)

        raise UnitNotFoundError(f"Unsupported expression type: {type(expr).__name__}")

    def _build_power_node(self, base_id: str, exponent: int) -> str:
        """Create or find a UnitPower node.

        Returns the ``node_id``.
        """
        from A_semantika._node_helpers import normalize_label_to_id

        now_iso = now()
        # Construct a deterministic node_id
        local_name = base_id.split(":")[-1]
        if exponent == 2:
            suffix = "_SQ"
        elif exponent == 3:
            suffix = "_CU"
        elif exponent == -1:
            suffix = "_RECIP"
        else:
            suffix = f"_POW{exponent}"
        node_id = f"unit:{local_name}{suffix}"

        # Check if already exists
        existing = self.node_svc.resolve_node_id_prefix(node_id)
        if existing:
            return existing["node_id"]

        etikedoj = json.dumps({
            "eo": f"{base_id.split(':')[-1]}^{exponent}",
            "en": f"{base_id.split(':')[-1]}^{exponent}",
        })
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (node_id, etikedoj, now_iso, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, 'rdf:type', ':UnitPower', 'uri', ?)",
            (node_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, ':hasBase', ?, 'uri', ?)",
            (node_id, base_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, ':hasExponent', ?, 'literal', ?)",
            (node_id, str(exponent), now_iso),
        )
        return node_id

    def _build_product_node(self, term_ids: list[str]) -> str:
        """Create or find a UnitProduct node.

        Binary decomposition: repeated UnitProduct(term1, term2).
        Returns the ``node_id`` of the outermost product.
        """
        if len(term_ids) == 1:
            return term_ids[0]

        # For two terms, build a single UnitProduct
        if len(term_ids) == 2:
            return self._build_binary_product(term_ids[0], term_ids[1])

        # For N>2, chain: Product(a, Product(b, c))
        result = term_ids[-1]
        for tid in reversed(term_ids[:-1]):
            result = self._build_binary_product(tid, result)
        return result

    def _build_binary_product(self, term1_id: str, term2_id: str) -> str:
        """Create a binary UnitProduct node."""
        now_iso = now()
        # Deterministic name: sort terms so a*b == b*a
        terms_sorted = sorted([term1_id, term2_id])
        name1 = terms_sorted[0].split(":")[-1]
        name2 = terms_sorted[1].split(":")[-1]
        node_id = f"unit:{name1}_TIMES_{name2}"

        existing = self.node_svc.resolve_node_id_prefix(node_id)
        if existing:
            return existing["node_id"]

        etikedoj = json.dumps({
            "eo": f"{name1}·{name2}",
            "en": f"{name1}·{name2}",
        })
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (node_id, etikedoj, now_iso, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, 'rdf:type', ':UnitProduct', 'uri', ?)",
            (node_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, ':hasTerm1', ?, 'uri', ?)",
            (node_id, term1_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, ':hasTerm2', ?, 'uri', ?)",
            (node_id, term2_id, now_iso),
        )
        return node_id

    def _build_division_node(self, num_id: str, den_id: str) -> str:
        """Create or find a UnitDivision node."""
        now_iso = now()
        num_name = num_id.split(":")[-1]
        den_name = den_id.split(":")[-1]
        node_id = f"unit:{num_name}_PER_{den_name}"

        existing = self.node_svc.resolve_node_id_prefix(node_id)
        if existing:
            return existing["node_id"]

        etikedoj = json.dumps({
            "eo": f"{num_name}/{den_name}",
            "en": f"{num_name}/{den_name}",
        })
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (node_id, etikedoj, now_iso, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, 'rdf:type', ':UnitDivision', 'uri', ?)",
            (node_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, ':hasNumerator', ?, 'uri', ?)",
            (node_id, num_id, now_iso),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, ':hasDenominator', ?, 'uri', ?)",
            (node_id, den_id, now_iso),
        )
        return node_id

    # ── Public API ────────────────────────────────────────────────────

    def resolve_unit(self, expr: str) -> str:
        """Resolve a unit expression to a ``node_id``.

        Resolution chain:
          1. Try as an existing ``node_id`` prefix
          2. Parse as unit expression and auto-create compound nodes
          3. Raise ``UnitNotFoundError``

        Args:
            expr: Unit expression, e.g. ``"J"``, ``"K"``, ``"J/K"``, ``"kg*m/s^2"``.

        Returns:
            Resolved ``node_id``.

        Raises:
            UnitNotFoundError: If the unit cannot be found or created.
        """
        self._ensure_unit_initialised()

        # Phase 1: Try exact node_id first (to avoid prefix match like "unit:J" matching "unit:JOULE")
        node = self.db.execute_one(
            "SELECT * FROM nodes WHERE node_id = ? COLLATE NOCASE",
            (expr,),
        )
        if node:
            return node["node_id"]

        # Phase 1b: Try prefix match
        node = self.node_svc.resolve_node_id_prefix(expr)
        if node:
            return node["node_id"]

        # Phase 2: Try symbol lookup
        node = self._find_unit_by_symbol(expr)
        if node:
            return node["node_id"]

        # Phase 3: Try as expression → auto-create
        try:
            ast = parse(expr)
            return self._create_from_ast(ast)
        except (ValueError, UnitNotFoundError):
            raise
        except Exception as exc:
            raise UnitNotFoundError(
                f"Cannot resolve unit expression {expr!r}: {exc}"
            ) from exc

    def create_singleton(self, node_id: str, label: str, symbol: str) -> str:
        """Create a custom singular unit node.

        Args:
            node_id: Desired node ID (will be prefixed with ``unit:`` if not already).
            label: Human-readable label.
            symbol: Unit symbol.

        Returns:
            The created ``node_id``.
        """
        self._ensure_unit_initialised()
        if not node_id.startswith("unit:"):
            node_id = f"unit:{node_id}"

        now_iso = now()
        etikedoj = json.dumps({"eo": label, "en": label})
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES (?, ?, '', '{}', '', ?, ?)",
            (node_id, etikedoj, now_iso, now_iso),
        )
        # rdf:type SingularUnit
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, 'rdf:type', ':SingularUnit', 'uri', ?)",
            (node_id, now_iso),
        )
        # :symbol
        self.db.execute(
            "INSERT OR IGNORE INTO triples "
            "(subject_uuid, predicate_id, object_value, object_type, kreita_je) "
            "VALUES (?, ':symbol', ?, 'literal', ?)",
            (node_id, symbol, now_iso),
        )
        return node_id

    def list_units(self) -> list[dict]:
        """List all unit nodes (those with ``rdf:type :SingularUnit`` or compound types).

        Returns:
            List of node dicts augmented with ``unit_type`` and ``symbol`` fields.
        """
        self._ensure_unit_initialised()
        rows = self.db.execute(
            """SELECT DISTINCT n.* FROM nodes n
               JOIN triples t ON t.subject_uuid = n.node_id
               WHERE t.predicate_id = 'rdf:type'
                 AND t.object_value IN (
                     ':SingularUnit', ':PrefixedUnit', ':CompoundUnit',
                     ':UnitDivision', ':UnitProduct', ':UnitPower'
                 )
               ORDER BY n.node_id"""
        )
        result = []
        for row in rows:
            # Determine type and symbol from triples
            type_row = self.db.execute_one(
                "SELECT object_value FROM triples "
                "WHERE subject_uuid = ? AND predicate_id = 'rdf:type' "
                "AND object_type = 'uri' ORDER BY object_value LIMIT 1",
                (row["node_id"],),
            )
            sym_row = self.db.execute_one(
                "SELECT object_value FROM triples "
                "WHERE subject_uuid = ? AND predicate_id = ':symbol' "
                "AND object_type = 'literal'",
                (row["node_id"],),
            )
            row["unit_type"] = type_row["object_value"] if type_row else ""
            row["unit_symbol"] = sym_row["object_value"] if sym_row else ""
            result.append(row)
        return result

    def get_unit_info(self, node_id: str) -> dict | None:
        """Get detailed info for a unit node.

        Returns the node dict augmented with:
          - ``unit_type``: The ``rdf:type`` value
          - ``symbol``: The ``:symbol`` value
          - ``ucum``: The ``:ucumCode`` value
          - ``multiplier``: The ``:multiplier`` value (if any)
          - ``offset``: The ``:offset`` value (if any)
          - ``decomposition``: Human-readable decomposition string (for compound units)

        Args:
            node_id: The unit node ID.

        Returns:
            Augmented node dict, or ``None`` if not found.
        """
        self._ensure_unit_initialised()
        node = self.node_svc.resolve_node_id_prefix(node_id)
        if not node:
            return None

        # Get type
        type_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = 'rdf:type' "
            "AND object_type = 'uri' ORDER BY object_value LIMIT 1",
            (node["node_id"],),
        )
        node["unit_type"] = type_row["object_value"] if type_row else ""

        # Get symbol
        sym_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':symbol' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        node["symbol"] = sym_row["object_value"] if sym_row else ""

        # Get UCUM
        ucum_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':ucumCode' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        node["ucum"] = ucum_row["object_value"] if ucum_row else ""

        # Get multiplier
        mult_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':multiplier' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        node["multiplier"] = mult_row["object_value"] if mult_row else None

        # Get offset
        off_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':offset' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        node["offset"] = off_row["object_value"] if off_row else None

        # Get decomposition for compound units
        node["decomposition"] = self._get_decomposition(node["node_id"])

        return node

    def _get_decomposition(self, node_id: str) -> str:
        """Build a human-readable decomposition string for a unit.

        For compound units, traces through :hasNumerator/:hasDenominator
        etc. to produce something like ``"J / (K * kg)"``.
        """
        parts: list[str] = []

        # Check for UnitDivision
        num = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':hasNumerator' AND object_type = 'uri'",
            (node_id,),
        )
        den = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':hasDenominator' AND object_type = 'uri'",
            (node_id,),
        )
        if num and den:
            num_label = self._format_unit_ref(num["object_value"])
            den_label = self._format_unit_ref(den["object_value"])
            return f"{num_label} / {den_label}"

        # Check for UnitProduct
        t1 = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':hasTerm1' AND object_type = 'uri'",
            (node_id,),
        )
        t2 = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':hasTerm2' AND object_type = 'uri'",
            (node_id,),
        )
        if t1 and t2:
            t1_label = self._format_unit_ref(t1["object_value"])
            t2_label = self._format_unit_ref(t2["object_value"])
            return f"{t1_label} · {t2_label}"

        # Check for UnitPower
        base = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':hasBase' AND object_type = 'uri'",
            (node_id,),
        )
        exp = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':hasExponent' AND object_type = 'literal'",
            (node_id,),
        )
        if base and exp:
            base_label = self._format_unit_ref(base["object_value"])
            return f"{base_label}^{exp['object_value']}"

        return ""

    def _format_unit_ref(self, node_id: str) -> str:
        """Format a unit node reference for display.

        Uses symbol if available, otherwise the short node_id.
        """
        sym = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':symbol' AND object_type = 'literal'",
            (node_id,),
        )
        if sym:
            return sym["object_value"]
        # Fall back to short node_id
        return node_id.split(":")[-1] if ":" in node_id else node_id[:16]
