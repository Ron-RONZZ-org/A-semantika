"""Node preview table builders and confirmation dialogs.

Extracted from ``_preview.py`` during the 500-line monolith split.
Content columns use ``no_wrap=False`` for text wrapping (#19).
"""

from __future__ import annotations

from typing import Any

from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import info, tr_multi
from A.utils.interactive import confirm_action
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import NodeService
from A_semantika._preview_helpers import resolve_node_label, resolve_node_label_from_node, resolve_predicate_label
from A_semantika._predicate_service import PredicateService


def build_node_preview_table(node_id: str, labels: dict[str, str], defns: dict[str, str]) -> Table:
    """Build a preview table showing node metadata before creation.

    Args:
        node_id: The node ID to display.
        labels: Language->label dict (already parsed, not JSON).
        defns: Language->definition dict (already parsed, not JSON).

    Returns:
        A Rich Table with node details.
    """
    table = Table(show_header=False, box=BOX_SIMPLE)
    table.add_column(tr_multi("Detaloj", "Detail", "Detail"))
    table.add_column("")

    table.add_row(tr_multi("ID", "ID", "ID"), node_id if node_id else tr_multi(
        "(aUtomate generita)", "(auto-generated)", "(auto-genere)",
    ))

    if labels:
        labels_str = "\n".join(f"[{lang}] {val}" for lang, val in labels.items())
        table.add_row(tr_multi("Etikedoj", "Labels", "Etiquettes"), labels_str)

    if defns:
        defns_str = "\n".join(f"[{lang}] {val}" for lang, val in defns.items())
        table.add_row(tr_multi("Difinoj", "Definitions", "Definitions"), defns_str)

    return table


def build_node_modify_preview(
    node_id: str,
    old_labels: dict[str, str],
    new_labels: dict[str, str] | None,
    old_defns: dict[str, str],
    new_defns: dict[str, str] | None,
    old_arcs: list[dict] | None = None,
    new_arcs: list[dict] | None = None,
) -> Table | None:
    """Build a preview table showing old -> new values for a node modifi.

    Only includes fields that actually changed.  Returns ``None`` if no
    fields changed (no-op).

    Args:
        node_id: Node ID.
        old_labels: Existing labels dict.
        new_labels: New labels dict, or ``None`` if not changing.
        old_defns: Existing definitions dict.
        new_defns: New definitions dict, or ``None`` if not changing.
        old_arcs: Existing arcs (triples where node is subject), or ``None``.
        new_arcs: New arcs to add, or ``None``.  If not ``None``, arcs not
            present in *old_arcs* are shown as additions.

    Returns:
        A Rich Table with old->new columns, or ``None`` if nothing changed.
    """
    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Kampo", "Field", "Champ"))
    table.add_column(tr_multi("Malnova", "Old", "Ancien"))
    table.add_column(tr_multi("Nova", "New", "Nouveau"))

    has_changes = False

    if new_labels is not None and new_labels != old_labels:
        has_changes = True
        old_lines = "\n".join(f"[{k}] {v}" for k, v in sorted(old_labels.items())) if old_labels else "-"
        new_lines = "\n".join(f"[{k}] {v}" for k, v in sorted(new_labels.items())) if new_labels else "-"
        table.add_row(
            tr_multi("Etikedoj", "Labels", "Etiquettes"),
            old_lines,
            new_lines,
        )

    if new_defns is not None and new_defns != old_defns:
        has_changes = True
        old_lines = "\n".join(f"{k}: {v}" for k, v in sorted(old_defns.items())) if old_defns else "-"
        new_lines = "\n".join(f"{k}: {v}" for k, v in sorted(new_defns.items())) if new_defns else "-"
        table.add_row(
            tr_multi("Difinoj", "Definitions", "Definitions"),
            old_lines,
            new_lines,
        )

    if new_arcs is not None:
        old_arc_set = {
            (a["predicate"], a["object"]) for a in (old_arcs or [])
        }
        new_arc_set = {
            (a["predicate"], a["object"]) for a in new_arcs
        }
        added = new_arc_set - old_arc_set
        removed = old_arc_set - new_arc_set
        if added or removed:
            has_changes = True
            old_lines_lines: list[str] = []
            new_lines_lines: list[str] = []
            if removed:
                for pred, obj in sorted(removed):
                    old_lines_lines.append(f"{pred}: {truncate_uuid(obj) if obj else ''}")
            if added:
                for pred, obj in sorted(added):
                    new_lines_lines.append(f"{pred}: {truncate_uuid(obj) if obj else ''}")
            table.add_row(
                tr_multi("Arkoj", "Arcs", "Arcs"),
                "\n".join(old_lines_lines) if old_lines_lines else "-",
                "\n".join(new_lines_lines) if new_lines_lines else "-",
            )

    return table if has_changes else None


def confirm_node_creation(
    node_id: str,
    labels: dict[str, str],
    defns: dict[str, str],
    yes: bool = False,
) -> bool:
    """Show a confirmation prompt for creating a node (no arcs).

    Displays a Rich table with node details, then asks for confirmation.

    Args:
        node_id: The node ID.
        labels: Language->label dict.
        defns: Language->definition dict.
        yes: If True, skip confirmation.

    Returns:
        True if confirmed, False otherwise.
    """
    if yes:
        return True

    table = build_node_preview_table(node_id, labels, defns)

    info("")
    info(table)

    return confirm_action(
        tr_multi(
            "Cu krei tiun nodon?",
            "Create this node?",
            "Creer ce noeud ?",
        ),
        default=True,
    )


def confirm_node_with_arcs(
    node_svc: NodeService,
    pred_svc: PredicateService,
    node_label: str,
    node_uuid: str,
    arcs: list[dict[str, Any]],
    yes: bool = False,
) -> bool:
    """Show a confirmation prompt for creating a node with optional arcs.

    Args:
        node_label: Display label for the new node.
        node_uuid: UUID of the new node.
        arcs: List of arc dicts with keys:
              subject, predicate, object, object_type, object_lang,
              object_datatype, object_unit (all resolved).
        yes: If True, skip confirmation.

    Returns:
        True if confirmed, False otherwise.
    """
    if yes:
        return True

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("")
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"))
    table.add_column(tr_multi("Objekto", "Object", "Objet"))

    # Node summary row
    table.add_row(
        tr_multi("Nodo", "Node", "Noeud"),
        f"{node_label} ({truncate_uuid(node_uuid)})",
        "",
    )

    for i, arc in enumerate(arcs, 1):
        pred_label = resolve_predicate_label(pred_svc, arc["predicate"])
        if arc["object_type"] == "uri":
            obj_label = resolve_node_label(node_svc, arc["object"])
            table.add_row(
                f"Arc {i}",
                pred_label,
                obj_label,
            )
            raw_pred = arc["predicate"]
            raw_obj = truncate_uuid(arc["object"])
            table.add_row(
                "",
                raw_pred,
                raw_obj,
            )
        elif arc.get("object_datatype"):
            dtype = arc["object_datatype"].split(":")[-1]
            table.add_row(
                f"Arc {i}",
                pred_label,
                arc["object"],
            )
            raw_pred = arc["predicate"]
            table.add_row(
                "",
                raw_pred,
                f"({dtype})",
            )
        else:
            quoted = f'"{arc["object"]}"'
            table.add_row(
                f"Arc {i}",
                pred_label,
                quoted,
            )
            raw_pred = arc["predicate"]
            table.add_row(
                "",
                raw_pred,
                "",
            )

    info("")
    info(table)

    arc_count = len(arcs)
    return confirm_action(
        tr_multi(
            f"Cu krei nodon kun {arc_count} arkoj?",
            f"Create node with {arc_count} arcs?",
            f"Creer le noeud avec {arc_count} arcs ?",
        ),
        default=True,
    )
