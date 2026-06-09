"""Compound unit node creation from AST + singleton creation.

Extracted from ``_unit_service.py`` to keep that file under 500 lines.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable

from A_semantika._unit_parser import (
    SingularUnit,
    UnitExpression,
    UnitPower,
    UnitProduct,
    normalize,
)
from A_semantika._unit_errors import UnitNotFoundError

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A.data.base import SQLiteDB


class UnitBuilder:
    """Creates compound unit nodes from parsed expressions.

    Isolated from :class:`UnitService` to keep monolith splitting clean.
    Requires a ``resolve_word`` callable (typically
    ``UnitService._resolve_word_to_node``) to resolve token names during
    AST walk.
    """

    def __init__(
        self,
        db: SQLiteDB,
        node_svc: NodeService,
        resolve_word_fn: Callable[[str], dict],
    ) -> None:
        self.db = db
        self.node_svc = node_svc
        self._resolve_word_to_node = resolve_word_fn

    def create_from_ast(self, expr: UnitExpression) -> str:
        """Walk an AST and create missing compound unit nodes.

        Returns the ``node_id`` of the root unit.
        """
        expr = normalize(expr)

        if isinstance(expr, SingularUnit):
            node = self._resolve_word_to_node(expr.name)
            return node["node_id"]

        if isinstance(expr, UnitPower):
            base_id = self.create_from_ast(expr.base)
            return self._build_power_node(base_id, expr.exponent)

        if isinstance(expr, UnitProduct):
            term_ids: list[str] = []
            for term in expr.terms:
                term_id = self.create_from_ast(term)
                term_ids.append(term_id)
            return self._build_product_node(term_ids)

        raise UnitNotFoundError(f"Unsupported expression type: {type(expr).__name__}")

    def _build_power_node(self, base_id: str, exponent: int) -> str:
        """Create or find a UnitPower node.

        Returns the ``node_id``.
        """
        from A_semantika._node_helpers import normalize_label_to_id  # noqa: F401
        from A_semantika.data.storage import now

        now_iso = now()
        # Construct a deterministic node_id
        local_name = base_id.split(":")[-1]
        if exponent == 2:
            suffix = "_SQ"
        elif exponent == 3:
            suffix = "_CU"
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
        from A_semantika.data.storage import now

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

    def create_singleton(self, node_id: str, label: str, symbol: str) -> str:
        """Create a custom singular unit node.

        Args:
            node_id: Desired node ID (will be prefixed with ``unit:`` if not already).
            label: Human-readable label.
            symbol: Unit symbol.

        Returns:
            The created ``node_id``.
        """
        from A_semantika.data.storage import now

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
