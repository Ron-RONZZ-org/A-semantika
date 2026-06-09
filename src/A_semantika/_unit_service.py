"""UnitService — facade for unit ontology operations.

Provides unit node creation, expression-based auto-creation,
decomposition, and the core ``resolve_unit()`` chain used by CLI ``-u`` flags.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from A_semantika._node_helpers import AmbiguousUUIDError, extract_label_text
from A_semantika._unit_builder import UnitBuilder
from A_semantika._unit_decomposition import UnitDecomposer, format_unit_ref
from A_semantika._unit_errors import UnitNotFoundError
from A_semantika._unit_parser import parse
from A_semantika._unit_seed_data import ALL_UNITS, BASE_AND_DERIVED, SI_BASE_UNITS
from A_semantika.data.storage import now

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._triple_service import TripleService
    from A.data.base import SQLiteDB


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
        self._builder: UnitBuilder | None = None
        self._decomposer: UnitDecomposer | None = None

    # ── Private helpers ──────────────────────────────────────────────

    @property
    def builder(self) -> UnitBuilder:
        if self._builder is None:
            self._builder = UnitBuilder(self.db, self.node_svc, self._resolve_word_to_node)
        return self._builder

    @property
    def decomposer(self) -> UnitDecomposer:
        if self._decomposer is None:
            self._decomposer = UnitDecomposer(self.db)
        return self._decomposer

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
        for prefix_data in ALL_UNITS[len(BASE_AND_DERIVED):]:
            self._insert_unit_node(prefix_data, now_iso)
        self._base_units_ensured = True

    def _insert_unit_node(self, unit: dict, now_iso: str) -> None:
        """Insert a unit node with its type, symbol, and UCUM triples."""
        etikedoj = json.dumps(unit["etikedoj"])
        label_text = extract_label_text(unit["etikedoj"])
        self.db.execute(
            "INSERT OR IGNORE INTO nodes "
            "(node_id, etikedoj, label_text, difinoj, difin_text, kreita_je, modifita_je) "
            "VALUES (?, ?, ?, '{}', '', ?, ?)",
            (unit["node_id"], etikedoj, label_text, now_iso, now_iso),
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
          1. Try as an exact ``node_id`` match (falls through on ambiguous)
          2. Try as a ``:symbol`` triple value
          3. Try as a label / FTS5 search
        """
        # Phase 1: exact node_id
        try:
            node = self.node_svc.resolve_node_id_prefix(word)
            if node:
                return node
        except AmbiguousUUIDError:
            # Short prefixes like "J" or "K" can match multiple node_ids;
            # fall through to symbol lookup instead of failing
            pass

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

        # Phase 1: Try exact node_id first
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
            return self.builder.create_from_ast(ast)
        except (ValueError, UnitNotFoundError):
            raise
        except Exception as exc:
            raise UnitNotFoundError(
                f"Cannot resolve unit expression {expr!r}: {exc}"
            ) from exc

    def normalize_unit(self, node_id_or_symbol: str) -> str:
        """Return the canonical ``node_id`` for a unit without auto-creating.

        Pure read-only lookup.  Unlike :meth:`resolve_unit`, this never
        creates compound unit nodes or parses expressions.  It resolves:
          1. Exact ``node_id`` match
          2. ``:symbol`` triple lookup
          3. FTS5 label search (exactly 1 result only)

        Args:
            node_id_or_symbol: A unit node ID, symbol, or label.

        Returns:
            The canonical ``node_id`` if found, or the original input if
            resolution fails (graceful fallback for no-op detection).
        """
        self._ensure_unit_initialised()

        # Phase 1: Exact node_id match
        node = self.db.execute_one(
            "SELECT * FROM nodes WHERE node_id = ? COLLATE NOCASE",
            (node_id_or_symbol,),
        )
        if node:
            return node["node_id"]

        # Phase 2: Prefix match
        node = self.node_svc.resolve_node_id_prefix(node_id_or_symbol)
        if node:
            return node["node_id"]

        # Phase 3: Symbol lookup
        node = self._find_unit_by_symbol(node_id_or_symbol)
        if node:
            return node["node_id"]

        # Phase 4: FTS5 label search (exactly 1 result only)
        results = self.node_svc.search(node_id_or_symbol, limit=2)
        if len(results) == 1:
            return results[0]["node_id"]

        # Graceful fallback: return input unchanged
        return node_id_or_symbol

    def create_singleton(self, node_id: str, label: str, symbol: str) -> str:
        """Create a custom singular unit node.

        Delegates to :class:`UnitBuilder`.  See its
        :meth:`~UnitBuilder.create_singleton` for details.
        """
        self._ensure_unit_initialised()
        return self.builder.create_singleton(node_id, label, symbol)

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
                     ':UnitProduct', ':UnitPower'
                 )
               ORDER BY n.node_id"""
        )
        result = []
        for row in rows:
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

        type_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = 'rdf:type' "
            "AND object_type = 'uri' ORDER BY object_value LIMIT 1",
            (node["node_id"],),
        )
        node["unit_type"] = type_row["object_value"] if type_row else ""

        sym_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':symbol' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        node["symbol"] = sym_row["object_value"] if sym_row else ""

        ucum_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':ucumCode' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        node["ucum"] = ucum_row["object_value"] if ucum_row else ""

        mult_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':multiplier' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        node["multiplier"] = mult_row["object_value"] if mult_row else None

        off_row = self.db.execute_one(
            "SELECT object_value FROM triples "
            "WHERE subject_uuid = ? AND predicate_id = ':offset' "
            "AND object_type = 'literal'",
            (node["node_id"],),
        )
        node["offset"] = off_row["object_value"] if off_row else None

        node["decomposition"] = self.decomposer.get_decomposition(node["node_id"])

        return node

    def _get_decomposition(self, node_id: str) -> str:
        """Backward-compat alias for :meth:`decomposer.get_decomposition`."""
        return self.decomposer.get_decomposition(node_id)

    def _decompose_product(self, term1_id: str, term2_id: str) -> str:
        """Backward-compat alias for :meth:`decomposer._decompose_product`."""
        return self.decomposer._decompose_product(term1_id, term2_id)

    def _format_unit_ref(self, node_id: str) -> str:
        """Backward-compat alias for :func:`format_unit_ref`."""
        return format_unit_ref(self.db, node_id)
