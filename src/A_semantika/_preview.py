"""Confirmation preview: Rich table builder + label resolution for triple display.

Used by all CLI 'aldoni' commands to show a formatted preview before
asking the user for confirmation.
"""
from __future__ import annotations

import json
from typing import Any

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A.utils.interactive import confirm_action
from A_semantika._node_service import AmbiguousUUIDError, NodeService
from A_semantika._predicate_service import PredicateService
from A_semantika.data.storage import label_from_json


def resolve_node_label(node_svc: NodeService, uuid_or_prefix: str) -> str:
    """Resolve a node UUID/prefix to a display label.

    Delegates to NodeService.get_display_label() to avoid duplicating
    the eo→en→first fallback logic.

    Returns the label if found, the UUID prefix as fallback.

    Raises:
        AmbiguousUUIDError: If the prefix matches multiple nodes.
    """
    try:
        label, _ = node_svc.get_display_label(uuid_or_prefix)
        return label
    except AmbiguousUUIDError:
        raise
    except ValueError:
        return uuid_or_prefix[:8]


def resolve_predicate_label(pred_svc: PredicateService, predicate_id: str) -> str:
    """Resolve a predicate ID to a display label.

    Returns eo/en label from etikedoj JSON via label_from_json(),
    falling back to predicate_id if no label is available.
    Delegates to storage.label_from_json() to avoid duplicating
    the eo→en→first fallback logic.
    """
    pred = pred_svc.get_by_predicate_id(predicate_id)
    if not pred:
        return predicate_id
    etikedoj = pred.get("etikedoj", "{}")
    label = label_from_json(etikedoj)
    return label if label else predicate_id


def build_triple_preview_table(
    node_svc: NodeService,
    pred_svc: PredicateService,
    subject_uuid: str,
    predicate_id: str,
    object_value: str,
    object_type: str = "uri",
    object_lang: str | None = None,
    object_datatype: str | None = None,
    object_unit: str | None = None,
) -> tuple[Table, str]:
    """Build a Rich table preview for a single triple.

    Returns:
        Tuple of (Table, footnote_string).
    """
    table = Table(
        show_header=True,
        box=BOX_SIMPLE,
        header_style="bold",
    )
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=True)

    # Pre-resolve subject node once to avoid redundant DB calls
    try:
        subj_node = node_svc.resolve_uuid_prefix(subject_uuid)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua subjekto-prefikso: {e}", "Ambiguous subject prefix: {e}", "Préfixe sujet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    subj_id = subj_node["node_id"][:8] if subj_node else subject_uuid[:8]

    # Use resolve_node_label for subject display label
    subj_label = resolve_node_label(node_svc, subject_uuid)
    pred_label = resolve_predicate_label(pred_svc, predicate_id)

    if object_type == "uri":
        try:
            obj_node = node_svc.resolve_uuid_prefix(object_value)
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua objekto-prefikso: {e}", "Ambiguous object prefix: {e}", "Préfixe objet ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1) from e
        obj_id = obj_node["node_id"][:8] if obj_node else object_value[:8]
        # Labels row
        table.add_row(subj_label, pred_label, resolve_node_label(node_svc, object_value))
        # Raw IDs row
        lang_hint = ""
        if subj_node:
            try:
                labels_db = json.loads(subj_node["etikedoj"])
                for lang in ("eo", "en"):
                    val = labels_db.get(lang)
                    if val:
                        lang_hint = f" ({lang})"
                        break
            except (json.JSONDecodeError, TypeError):
                pass
        pred_id_display = predicate_id
        table.add_row(f"{subj_id}{lang_hint}", pred_id_display, obj_id)
        footnote = tr_multi("→ URI", "→ URI", "→ URI")
    elif object_type == "literal" and object_datatype:
        # Typed literal
        table.add_row(subj_label, pred_label, "")
        pred_id_display = predicate_id
        table.add_row(subj_id, pred_id_display, object_value)

        dtype = object_datatype.split(":")[-1] if ":" in object_datatype else object_datatype
        parts = [f"→ {dtype}"]
        if object_unit:
            unit_label = resolve_node_label(node_svc, object_unit)
            try:
                unit_node = node_svc.resolve_uuid_prefix(object_unit)
            except AmbiguousUUIDError as e:
                error(tr_multi("Ambigua unuo-prefikso: {e}", "Ambiguous unit prefix: {e}", "Préfixe unité ambigu : {e}").format(e=str(e)))
                raise typer.Exit(1) from e
            unit_id = unit_node["node_id"][:8] if unit_node else object_unit[:8]
            parts.append(f"unit: {unit_label} ({unit_id})")
        footnote = ", ".join(parts)
    else:
        # String literal
        table.add_row(subj_label, pred_label, "")
        pred_id_display = predicate_id
        quoted_val = f'"{object_value}"'
        table.add_row(subj_id, pred_id_display, quoted_val)

        parts = [tr_multi("→ literal", "→ literal", "→ litteral")]
        if object_lang:
            parts.append(f"lang: {object_lang}")
        footnote = ", ".join(parts)

    return table, footnote


def confirm_triple(
    node_svc: NodeService,
    pred_svc: PredicateService,
    subject_uuid: str,
    predicate_id: str,
    object_value: str,
    object_type: str = "uri",
    object_lang: str | None = None,
    object_datatype: str | None = None,
    object_unit: str | None = None,
    yes: bool = False,
) -> bool:
    """Show a confirmation prompt for adding a triple.

    Displays a Rich table preview, then asks for confirmation.

    Args:
        yes: If True, skip confirmation.

    Returns:
        True if confirmed, False otherwise.
    """
    if yes:
        return True

    table, footnote = build_triple_preview_table(
        node_svc, pred_svc,
        subject_uuid, predicate_id, object_value,
        object_type, object_lang, object_datatype, object_unit,
    )

    info("")
    info(table)
    info(footnote)

    return confirm_action(
        tr_multi(
            "Ĉu krei tiun arkon?",
            "Create this arc?",
            "Créer cet arc ?",
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
    table.add_column("", no_wrap=True)
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=True)

    # Node summary row
    table.add_row(
        tr_multi("Nodo", "Node", "Noeud"),
        f"{node_label} ({node_uuid[:8]})",
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
            raw_obj = arc["object"][:8]
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
            f"Ĉu krei nodon kun {arc_count} arkoj?",
            f"Create node with {arc_count} arcs?",
            f"Créer le nœud avec {arc_count} arcs ?",
        ),
        default=True,
    )
