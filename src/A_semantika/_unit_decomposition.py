"""Unit decomposition helpers — human-readable display strings.

Extracted from ``_unit_service.py`` to keep that file under 500 lines.
Walks compound unit structures (UnitPower, UnitProduct) and produces
readable strings like ``"J / (K * kg)"``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from A.data.base import SQLiteDB


def format_unit_ref(db: SQLiteDB, node_id: str) -> str:
    """Format a unit node reference for display.

    Uses symbol if available, otherwise the short node_id.
    """
    sym = db.execute_one(
        "SELECT object_value FROM triples "
        "WHERE subject_uuid = ? AND predicate_id = ':symbol' AND object_type = 'literal'",
        (node_id,),
    )
    if sym:
        return sym["object_value"]
    # Fall back to short node_id
    return node_id.split(":")[-1] if ":" in node_id else node_id[:16]


class UnitDecomposer:
    """Builds human-readable decomposition strings for compound units.

    Uses ``db`` directly (no service layer) — pure data querying.
    """

    def __init__(self, db: SQLiteDB) -> None:
        self.db = db

    def get_decomposition(self, node_id: str) -> str:
        """Build a human-readable decomposition string for a unit.

        Walks the compound unit structure to produce something like
        ``"J / (K * kg)"``, detecting negative exponents to show
        division for readability.
        """
        # Check for UnitPower first (catches standalone negative exponents)
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
            base_label = format_unit_ref(self.db, base["object_value"])
            return f"{base_label}^{exp['object_value']}"

        # Check for UnitProduct — split terms by exponent sign
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
            return self._decompose_product(t1["object_value"], t2["object_value"])

        # Fallback: legacy :hasNumerator/:hasDenominator (from old DB data)
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
            num_label = format_unit_ref(self.db, num["object_value"])
            den_label = format_unit_ref(self.db, den["object_value"])
            return f"{num_label} / {den_label}"

        return ""

    def _decompose_product(self, term1_id: str, term2_id: str) -> str:
        """Decompose a binary product, detecting negative exponents.

        Terms with negative exponents move to the denominator side
        for human-readable display (e.g. ``J / K`` instead of ``J * K^-1``).
        """
        num_parts: list[str] = []
        den_parts: list[str] = []

        for tid in (term1_id, term2_id):
            # Check if this term is a UnitPower with negative exponent
            t_exp = self.db.execute_one(
                "SELECT object_value FROM triples "
                "WHERE subject_uuid = ? AND predicate_id = ':hasExponent' AND object_type = 'literal'",
                (tid,),
            )
            if t_exp and t_exp["object_value"].startswith("-"):
                # Negative exponent → denominator side (invert for display)
                pos_exp = t_exp["object_value"][1:]
                base = self.db.execute_one(
                    "SELECT object_value FROM triples "
                    "WHERE subject_uuid = ? AND predicate_id = ':hasBase' AND object_type = 'uri'",
                    (tid,),
                )
                if base:
                    label = format_unit_ref(self.db, base["object_value"])
                    den_parts.append(f"{label}^{pos_exp}" if pos_exp != "1" else label)
                else:
                    den_parts.append(format_unit_ref(self.db, tid))
            else:
                # Positive exponent or simple unit → numerator
                label = format_unit_ref(self.db, tid)
                num_parts.append(label)

        num_str = " · ".join(num_parts) if num_parts else "1"
        den_str = " · ".join(den_parts)
        if not den_parts:
            return num_str
        if len(den_parts) > 1:
            den_str = f"({den_str})"
        return f"{num_str} / {den_str}"
