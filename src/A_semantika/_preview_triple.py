"""Triple preview table builder and confirmation dialog.

Extracted from ``_preview.py`` during the 500-line monolith split.
"""

from __future__ import annotations

import json
from typing import Any

from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._node_helpers import AmbiguousUUIDError, truncate_uuid
from A_semantika._node_service import NodeService
from A_semantika._preview_helpers import resolve_node_label, resolve_node_label_from_node, resolve_predicate_label
from A_semantika._predicate_service import PredicateService


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
) -> tuple[Table | None, str]:
    """Build a Rich table preview for a single triple.

    Returns:
        Tuple of (Table or None if ambiguous, footnote_string).
        When the table is None, the caller should handle the error
        (e.g. show a message and exit) rather than letting this
        helper raise a CLI-level exception.
    """
    table = Table(
        show_header=True,
        box=BOX_SIMPLE,
        header_style="bold",
    )
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=False)
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=False)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=False)

    # Pre-resolve subject node once, then use cached data for both
    # display label and raw ID (avoids redundant DB calls).
    try:
        subj_node = node_svc.resolve_node_id_prefix(subject_uuid)
    except AmbiguousUUIDError as e:
        warning(tr_multi("Ambigua subjekto-prefikso: {e}", "Ambiguous subject prefix: {e}", "Prefixe sujet ambigu : {e}").format(e=str(e)))
        return None, ""
    subj_id = truncate_uuid(subj_node["node_id"]) if subj_node else truncate_uuid(subject_uuid)
    subj_label = resolve_node_label_from_node(subj_node) if subj_node else truncate_uuid(subject_uuid)

    pred_label = resolve_predicate_label(pred_svc, predicate_id)

    if object_type == "uri":
        try:
            obj_node = node_svc.resolve_node_id_prefix(object_value)
        except AmbiguousUUIDError as e:
            warning(tr_multi("Ambigua objekto-prefikso: {e}", "Ambiguous object prefix: {e}", "Prefixe objet ambigu : {e}").format(e=str(e)))
            return None, ""
        obj_id = truncate_uuid(obj_node["node_id"]) if obj_node else truncate_uuid(object_value)
        obj_label = resolve_node_label_from_node(obj_node) if obj_node else truncate_uuid(object_value)
        # Labels row
        table.add_row(subj_label, pred_label, obj_label)
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
        table.add_row(f"{subj_id}{lang_hint}", predicate_id, obj_id)
        footnote = tr_multi("→ URI", "→ URI", "→ URI")

    elif object_type == "literal" and object_datatype:
        # Typed literal
        dtype = object_datatype.split(":")[-1] if ":" in object_datatype else object_datatype
        obj_display = tr_multi(
            "Tipita literal ({d})", "Typed literal ({d})", "Litteral type ({d})",
        ).format(d=dtype)
        table.add_row(subj_label, pred_label, object_value)
        table.add_row(subj_id, predicate_id, obj_display)

        parts = [f"→ {dtype}"]
        if object_unit:
            try:
                unit_node = node_svc.resolve_node_id_prefix(object_unit)
            except AmbiguousUUIDError as e:
                warning(tr_multi("Ambigua unuo-prefikso: {e}", "Ambiguous unit prefix: {e}", "Prefixe unite ambigu : {e}").format(e=str(e)))
                return None, ""
            unit_label = resolve_node_label_from_node(unit_node) if unit_node else truncate_uuid(object_unit)
            unit_id = truncate_uuid(unit_node["node_id"]) if unit_node else truncate_uuid(object_unit)
            parts.append(f"unit: {unit_label} ({unit_id})")
        footnote = ", ".join(parts)
    else:
        # String literal
        quoted_val = f'"{object_value}"'
        table.add_row(subj_label, pred_label, quoted_val)
        lang_info = (
            tr_multi(
                "literal, lingvo: {l}", "literal, lang: {l}", "litteral, langue : {l}",
            ).format(l=object_lang)
            if object_lang
            else tr_multi("literal", "literal", "litteral")
        )
        table.add_row(subj_id, predicate_id, lang_info)
        footnote = ""

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

    if table is None:
        return False

    info("")
    info(table)
    info(footnote)

    return confirm_action(
        tr_multi(
            "Cu krei tiun arkon?",
            "Create this arc?",
            "Creer cet arc ?",
        ),
        default=True,
    )
