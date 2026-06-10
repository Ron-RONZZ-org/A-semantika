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
from A_semantika.data.storage import KATEX_DATATYPE




def format_tipo(
    object_type: str,
    object_datatype: str | None = None,
    object_lang: str | None = None,
    object_unit_display: str | None = None,
) -> str:
    """Map (object_type, object_datatype) to a localized type display string.

    Returns a short localized label for the Tipo (Type) column in search
    results, preview tables, and interactive pickers.

    If *object_unit_display* is provided and the type is a numeric XSD type
    (integer or decimal), the unit symbol is appended in parentheses.
    The unit symbol must be pre-resolved from the caller.

    Examples:
        format_tipo("uri")                                            → "nodreferenco"
        format_tipo("literal")                                        → "teksto"
        format_tipo("literal", "xsd:integer")                         → "entjero"
        format_tipo("literal", "xsd:integer", object_unit_display="C") → "entjero (C)"
        format_tipo("literal", KATEX_DATATYPE)                        → "katex (formulo)"
        format_tipo("literal", "text/x-python")                       → "kodo (python)"
        format_tipo("literal", object_lang="eo")                      → "teksto (eo)"
    """
    if object_type == "uri":
        return tr_multi("nodreferenco", "node ref", "réf. nœud")

    if object_datatype == KATEX_DATATYPE:
        return tr_multi("katex (formulo)", "katex (formula)", "katex (formule)")

    if object_datatype:
        if object_datatype.startswith("text/") or object_datatype.startswith("application/"):
            lang_display = object_datatype.split("/")[-1]
            lang_display = lang_display.replace("x-", "", 1) if lang_display.startswith("x-") else lang_display
            return tr_multi(
                "kodo ({l})", "code ({l})", "code ({l})",
            ).format(l=lang_display)

        # Standard XSD types
        dtype = object_datatype.split(":")[-1] if ":" in object_datatype else object_datatype
        xsd_labels: dict[str, tuple[str, str, str]] = {
            "integer": ("entjero", "integer", "entier"),
            "decimal": ("decimalo", "decimal", "décimal"),
            "boolean": ("bulea", "boolean", "booléen"),
        }
        if dtype in xsd_labels:
            eo, en, fr = xsd_labels[dtype]
            base = tr_multi(eo, en, fr)
            if object_unit_display and dtype in ("integer", "decimal"):
                return f"{base} ({object_unit_display})"
            return base
        # Fallback: show raw datatype suffix
        return dtype

    # Plain string literal (no datatype)
    if object_lang:
        return tr_multi(
            "teksto ({l})", "string ({l})", "chaîne ({l})",
        ).format(l=object_lang)
    return tr_multi("teksto", "string", "chaîne")

def _get_lang_hint(node: dict | None) -> str:
    """Extract a language hint string from a node's etikedoj.

    Returns ``"(eo)"``, ``"(en)"``, or ``""`` if no matching language found.
    """
    if not node:
        return ""
    try:
        labels = json.loads(node.get("etikedoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        return ""
    for lang in ("eo", "en"):
        if labels.get(lang):
            return f" ({lang})"
    return ""


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
    # Language hint for subject label (applied in all branches)
    subj_hint = _get_lang_hint(subj_node)
    subj_label_display = f"{subj_label}{subj_hint}" if subj_hint else subj_label

    pred_label = resolve_predicate_label(pred_svc, predicate_id)

    if object_type == "uri":
        try:
            obj_node = node_svc.resolve_node_id_prefix(object_value)
        except AmbiguousUUIDError as e:
            warning(tr_multi("Ambigua objekto-prefikso: {e}", "Ambiguous object prefix: {e}", "Prefixe objet ambigu : {e}").format(e=str(e)))
            return None, ""
        obj_id = truncate_uuid(obj_node["node_id"]) if obj_node else truncate_uuid(object_value)
        obj_label = resolve_node_label_from_node(obj_node) if obj_node else truncate_uuid(object_value)
        # Object language hint
        obj_hint = _get_lang_hint(obj_node)
        obj_label_display = f"{obj_label}{obj_hint}" if obj_hint else obj_label
        # Labels row with language hints
        table.add_row(subj_label_display, pred_label, obj_label_display)
        # Raw IDs row (no language hints)
        table.add_row(subj_id, predicate_id, obj_id)
        footnote = tr_multi("→ URI", "→ URI", "→ URI")

    elif object_type == "literal" and object_datatype:
        if object_datatype == KATEX_DATATYPE:
            # KaTeX formula: show full formula so user can verify before confirming
            table.add_row(subj_label_display, pred_label, object_value)
            table.add_row(subj_id, predicate_id, "→ katex formula")
            footnote = tr_multi("→ KaTeX", "→ KaTeX", "→ KaTeX")
        elif object_datatype.startswith("text/") or object_datatype.startswith("application/"):
            # Code block (MIME typed literal): show full content so user can verify
            lang_display = object_datatype.split("/")[-1]  # "x-python" -> "x-python"
            lang_display = lang_display.replace("x-", "", 1) if lang_display.startswith("x-") else lang_display
            char_count = len(object_value)
            table.add_row(subj_label_display, pred_label, object_value)
            table.add_row(subj_id, predicate_id, f"→ {object_datatype}, {char_count} chars")
            footnote = tr_multi(
                "→ {lang}, {n} znakoj", "→ {lang}, {n} chars", "→ {lang}, {n} car.",
            ).format(lang=lang_display, n=char_count)
        else:
            # Standard typed literal (xsd:integer, xsd:decimal, xsd:boolean)
            dtype = object_datatype.split(":")[-1] if ":" in object_datatype else object_datatype
            obj_display = tr_multi(
                "Tipita literal ({d})", "Typed literal ({d})", "Litteral type ({d})",
            ).format(d=dtype)
            table.add_row(subj_label_display, pred_label, object_value)
            table.add_row(subj_id, predicate_id, obj_display)

            parts = [f"→ {dtype}"]
            if object_unit:
                try:
                    unit_node = node_svc.resolve_node_id_prefix(object_unit)
                except AmbiguousUUIDError as e:
                    warning(tr_multi("Ambigua unuo-prefikso: {e}", "Ambiguous unit prefix: {e}", "Prefixe unité ambigu : {e}").format(e=str(e)))
                    return None, ""
                # Look up unit symbol via :symbol triple for a more informative display
                if unit_node:
                    sym_row = node_svc.db.execute_one(
                        "SELECT object_value FROM triples "
                        "WHERE subject_uuid = ? AND predicate_id = ':symbol' "
                        "AND object_type = 'literal'",
                        (unit_node["node_id"],),
                    )
                    if sym_row:
                        unit_display = f"{sym_row['object_value']} ({truncate_uuid(unit_node['node_id'])})"
                    else:
                        unit_display = resolve_node_label_from_node(unit_node)
                else:
                    unit_display = truncate_uuid(object_unit)
                parts.append(f"unit: {unit_display}")
            footnote = ", ".join(parts)
    else:
        # String literal
        quoted_val = f'"{object_value}"'
        table.add_row(subj_label_display, pred_label, quoted_val)
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


def build_metadata_diff_table(
    existing: dict,
    object_lang: str | None = None,
    object_datatype: str | None = None,
    object_unit: str | None = None,
) -> Table | None:
    """Build a compact diff table for triple metadata changes.

    Only shows rows for fields that actually differ from the existing triple.
    Returns ``None`` if no fields differ.

    Args:
        existing: Existing triple dict.
        object_lang: New language tag (or None to keep existing).
        object_datatype: New datatype (or None to keep existing).
        object_unit: New unit node ID (or None to keep existing).
    """
    old_lang = existing.get("object_lang")
    old_dtype = existing.get("object_datatype")
    old_unit = existing.get("object_unit")

    rows: list[tuple[str, str, str]] = []
    if object_lang is not None and object_lang != old_lang:
        rows.append((
            tr_multi("Lingvo", "Language", "Langue"),
            old_lang or tr_multi("(nenio)", "(none)", "(aucun)"),
            object_lang or tr_multi("(nenio)", "(none)", "(aucun)"),
        ))
    if object_datatype is not None and object_datatype != old_dtype:
        rows.append((
            tr_multi("Datatype", "Datatype", "Datatype"),
            old_dtype or tr_multi("(nenio)", "(none)", "(aucun)"),
            object_datatype or tr_multi("(nenio)", "(none)", "(aucun)"),
        ))
    if object_unit is not None and object_unit != old_unit:
        rows.append((
            tr_multi("Unuo", "Unit", "Unité"),
            old_unit or tr_multi("(nenio)", "(none)", "(aucun)"),
            object_unit or tr_multi("(nenio)", "(none)", "(aucun)"),
        ))

    if not rows:
        return None

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Kampo", "Field", "Champ"), no_wrap=True)
    table.add_column(tr_multi("Malnova", "Old", "Ancien"), no_wrap=False)
    table.add_column(tr_multi("Nova", "New", "Nouveau"), no_wrap=False)
    for field, old_val, new_val in rows:
        table.add_row(field, old_val, new_val)
    return table


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
