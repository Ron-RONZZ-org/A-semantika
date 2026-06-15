"""Preview helpers for proof (provo) operations.

Provides Rich table builders for proof creation confirmation and
proof listing display.
"""
from __future__ import annotations

from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import tr_multi
from A_semantika._node_helpers import truncate_uuid


def build_proof_confirm_table(
    subject_label: str,
    subject_id: str,
    predicate_label: str,
    predicate_id: str,
    object_label: str,
    object_id: str,
    object_type: str,
    proof_preview: str,
    is_update: bool = False,
) -> tuple[Table, str]:
    """Build a Rich table preview for a proof creation confirmation.

    Shows the target arc (labels + raw IDs) and a preview of the
    proof text (first 80 chars with ellipsis).

    Args:
        subject_label: Display label of the subject node.
        subject_id: Subject node_id.
        predicate_label: Display label of the predicate.
        predicate_id: Predicate ID.
        object_label: Display label or raw literal value.
        object_id: Object node_id or literal value.
        object_type: 'uri' or 'literal'.
        proof_preview: Truncated preview of the proof text.
        is_update: If True, shows "update proof" instead of "new proof".

    Returns:
        Tuple of (Table, locale_key) where locale_key is used for
        the confirmation prompt text.
    """
    table = Table(
        show_header=True,
        box=BOX_SIMPLE,
        header_style="bold",
        title=tr_multi(
            "Aldoni pruvon" if not is_update else "Ĝisdatigi pruvon",
            "Add proof" if not is_update else "Update proof",
            "Ajouter une preuve" if not is_update else "Mettre à jour la preuve",
        ),
    )
    table.add_column(tr_multi("Kampo", "Field", "Champ"), no_wrap=True)
    table.add_column(tr_multi("Valoro", "Value", "Valeur"), no_wrap=False)

    # Target arc
    table.add_row(
        tr_multi("Arko", "Arc", "Arc"),
        f"{subject_label} --{predicate_label}--> {object_label}",
    )
    table.add_row(
        tr_multi("Subjekto ID", "Subject ID", "ID Sujet"),
        truncate_uuid(subject_id),
    )
    table.add_row(
        tr_multi("Predikato ID", "Predicate ID", "ID Prédicat"),
        predicate_id,
    )
    if object_type == "uri":
        table.add_row(
            tr_multi("Objekto ID", "Object ID", "ID Objet"),
            truncate_uuid(object_id),
        )
    else:
        table.add_row(
            tr_multi("Objekto tipo", "Object type", "Type objet"),
            tr_multi("literalo", "literal", "littéral"),
        )

    table.add_row(
        tr_multi("Pruva antaŭrigardo", "Proof preview", "Aperçu de la preuve"),
        proof_preview[:80] + ("..." if len(proof_preview) > 80 else ""),
    )

    footnote = tr_multi(
        "→ markdown" if not is_update else "→ anstataŭigi ekzistantan pruvon",
        "→ markdown" if not is_update else "→ replace existing proof",
        "→ markdown" if not is_update else "→ remplacer la preuve existante",
    )

    return table, footnote


def build_proof_list_table(
    proofs: list[dict],
    stmt_ids: list[str] | None = None,
) -> Table | None:
    """Build a Rich table listing proofs for an arc.

    Args:
        proofs: List of proof dicts with 'stmt_node_id', 'proof_text'.
        stmt_ids: Optional pre-filtered list of statement node IDs to show.

    Returns:
        A Rich Table, or None if no proofs to display.
    """
    if not proofs:
        return None

    # Filter if stmt_ids given
    if stmt_ids:
        stmt_set = set(stmt_ids)
        proofs = [p for p in proofs if p["stmt_node_id"] in stmt_set]

    if not proofs:
        return None

    table = Table(
        show_header=True,
        box=BOX_SIMPLE,
        header_style="bold",
    )
    table.add_column(
        tr_multi("Pruva Nodo", "Proof Node", "Nœud Preuve"), no_wrap=True,
    )
    table.add_column(
        tr_multi("Enhavaĵo", "Content", "Contenu"), no_wrap=False,
    )

    for p in proofs:
        stmt_preview = truncate_uuid(p["stmt_node_id"])
        text_preview = (p.get("proof_text") or "")[:60]
        if len(p.get("proof_text", "")) > 60:
            text_preview += "..."
        table.add_row(stmt_preview, text_preview)

    return table
