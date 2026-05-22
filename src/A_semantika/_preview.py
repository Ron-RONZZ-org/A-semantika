"""Confirmation preview: Rich table builder + label resolution for triple display.

Used by all CLI 'aldoni' commands to show a formatted preview before
asking the user for confirmation.
"""
from __future__ import annotations

import json
from typing import Any

from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import tr_multi
from A.utils.interactive import confirm_action
from A_semantika._node_service import NodeService
from A_semantika._predicate_service import PredicateService


def resolve_node_label(node_svc: NodeService, uuid_or_prefix: str) -> str:
    """Resolve a node UUID/prefix to a display label.

    Returns the label if found, the UUID prefix as fallback.
    """
    try:
        node = node_svc.resolve_uuid_prefix(uuid_or_prefix)
    except ValueError:
        return uuid_or_prefix[:8]
    if not node:
        return uuid_or_prefix[:8]
    try:
        labels = json.loads(node["etikedoj"])
    except (json.JSONDecodeError, TypeError):
        return node["uuid"][:8]
    if not isinstance(labels, dict):
        return node["uuid"][:8]
    for lang in ("eo", "en"):
        val = labels.get(lang)
        if val and isinstance(val, str):
            return val
    for val in labels.values():
        if val and isinstance(val, str):
            return val
    return node["uuid"][:8]


def resolve_predicate_label(pred_svc: PredicateService, predicate_id: str) -> str:
    """Resolve a predicate ID to a display label.

    Returns label_eo or label_en, falling back to predicate_id.
    """
    pred = pred_svc.get_by_predicate_id(predicate_id)
    if not pred:
        return predicate_id
    return pred.get("label_eo") or pred.get("label_en") or predicate_id


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

    subj_label = resolve_node_label(node_svc, subject_uuid)
    pred_label = resolve_predicate_label(pred_svc, predicate_id)

    if object_type == "uri":
        obj_label = resolve_node_label(node_svc, object_value)
        # Labels row
        table.add_row(subj_label, pred_label, obj_label)
        # Raw IDs row
        n = node_svc.resolve_uuid_prefix(subject_uuid)
        subj_id = n["uuid"][:8] if n else subject_uuid[:8]
        lang_hint = ""
        lang_code = ""
        if n:
            try:
                labels = json.loads(n["etikedoj"])
                for lang in ("eo", "en"):
                    val = labels.get(lang)
                    if val:
                        lang_hint = f" ({lang})"
                        lang_code = lang
                        break
            except (json.JSONDecodeError, TypeError):
                pass
        p = pred_svc.get_by_predicate_id(predicate_id)
        pred_id_display = p["predicate_id"] if p else predicate_id
        obj_node = node_svc.resolve_uuid_prefix(object_value)
        obj_id = obj_node["uuid"][:8] if obj_node else object_value[:8]
        table.add_row(f"{subj_id}{lang_hint}", pred_id_display, obj_id)
        footnote = tr_multi("→ URI", "→ URI", "→ URI")
    elif object_type == "literal" and object_datatype:
        # Typed literal
        table.add_row(subj_label, pred_label, "")
        n = node_svc.resolve_uuid_prefix(subject_uuid)
        subj_id = n["uuid"][:8] if n else subject_uuid[:8]
        p = pred_svc.get_by_predicate_id(predicate_id)
        pred_id_display = p["predicate_id"] if p else predicate_id
        table.add_row(subj_id, pred_id_display, object_value)

        dtype = object_datatype.split(":")[-1] if ":" in object_datatype else object_datatype
        parts = [f"→ {dtype}"]
        if object_unit:
            unit_label = resolve_node_label(node_svc, object_unit)
            unit_node = node_svc.resolve_uuid_prefix(object_unit)
            unit_id = unit_node["uuid"][:8] if unit_node else object_unit[:8]
            parts.append(f"unit: {unit_label} ({unit_id})")
        footnote = ", ".join(parts)
    else:
        # String literal
        table.add_row(subj_label, pred_label, "")
        n = node_svc.resolve_uuid_prefix(subject_uuid)
        subj_id = n["uuid"][:8] if n else subject_uuid[:8]
        p = pred_svc.get_by_predicate_id(predicate_id)
        pred_id_display = p["predicate_id"] if p else predicate_id
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

    from A import info as _info

    _info("")
    _info(table)
    _info(footnote)

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

    from A import info as _info

    _info("")
    _info(table)

    arc_count = len(arcs)
    return confirm_action(
        tr_multi(
            f"Ĉu krei nodon kun {arc_count} arkoj?",
            f"Create node with {arc_count} arcs?",
            f"Créer le nœud avec {arc_count} arcs ?",
        ),
        default=True,
    )
