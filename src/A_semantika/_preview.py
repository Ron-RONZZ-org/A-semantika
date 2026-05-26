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

from A import error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._node_helpers import AmbiguousUUIDError, get_display_label, get_label_from_node
from A_semantika._node_service import NodeService
from A_semantika._predicate_service import PredicateService
from A_semantika.data.storage import label_from_json


def resolve_node_label(node_svc: NodeService, uuid_or_prefix: str, preferred_lang: str | None = None) -> str:
    """Resolve a node UUID/prefix to a display label.

    Delegates to ``get_display_label()`` from ``_node_helpers`` to avoid
    duplicating the label fallback logic.

    Args:
        node_svc: NodeService instance.
        uuid_or_prefix: Node ID or prefix.
        preferred_lang: Optional language code to try first
            (defaults to ``eo → en → first`` fallback).

    Returns the label if found, the UUID prefix as fallback.

    Raises:
        AmbiguousUUIDError: If the prefix matches multiple nodes.
    """
    try:
        label, _ = get_display_label(node_svc.resolve_node_id_prefix, uuid_or_prefix, preferred_lang)
        return label
    except AmbiguousUUIDError:
        raise
    except ValueError:
        return uuid_or_prefix[:16]


def resolve_node_label_from_node(node: dict, preferred_lang: str | None = None) -> str:
    """Get display label from a pre-resolved node dict.

    Avoids redundant ``node_svc.resolve_node_id_prefix()`` calls when the
    node dict has already been fetched (e.g. in ``build_triple_preview_table()``).

    Delegates to :func:`get_label_from_node` to share the same label
    fallback logic as :func:`resolve_node_label`.

    Args:
        node: Pre-resolved node dict.
        preferred_lang: Optional language code to try first.
    """
    return get_label_from_node(node, preferred_lang=preferred_lang)


def resolve_predicate_label(pred_svc: PredicateService, predicate_id: str, preferred_lang: str | None = None) -> str:
    """Resolve a predicate ID to a display label.

    Returns label in the preferred language (if given), otherwise
    ``eo → en → first`` fallback.  Falls back to predicate_id if no label
    is available.  Delegates to storage.label_from_json().

    Args:
        pred_svc: PredicateService instance.
        predicate_id: Predicate ID.
        preferred_lang: Optional language code to try first.
    """
    pred = pred_svc.get_by_predicate_id(predicate_id)
    if not pred:
        return predicate_id
    etikedoj = pred.get("etikedoj", "{}")
    lang_fallback = (preferred_lang, "eo", "en") if preferred_lang else ("eo", "en")
    label = label_from_json(etikedoj, lang_fallback)
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
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=True)

    # Pre-resolve subject node once, then use cached data for both
    # display label and raw ID (avoids redundant DB calls).
    try:
        subj_node = node_svc.resolve_node_id_prefix(subject_uuid)
    except AmbiguousUUIDError as e:
        warning(tr_multi("Ambigua subjekto-prefikso: {e}", "Ambiguous subject prefix: {e}", "Préfixe sujet ambigu : {e}").format(e=str(e)))
        return None, ""
    subj_id = subj_node["node_id"][:16] if subj_node else subject_uuid[:16]
    subj_label = resolve_node_label_from_node(subj_node) if subj_node else subject_uuid[:16]

    pred_label = resolve_predicate_label(pred_svc, predicate_id)

    if object_type == "uri":
        # Resolve object node once, use cached data
        try:
            obj_node = node_svc.resolve_node_id_prefix(object_value)
        except AmbiguousUUIDError as e:
            warning(tr_multi("Ambigua objekto-prefikso: {e}", "Ambiguous object prefix: {e}", "Préfixe objet ambigu : {e}").format(e=str(e)))
            return None, ""
        obj_id = obj_node["node_id"][:16] if obj_node else object_value[:16]
        obj_label = resolve_node_label_from_node(obj_node) if obj_node else object_value[:16]
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
        # Typed literal — use cached subj_node for label
        dtype = object_datatype.split(":")[-1] if ":" in object_datatype else object_datatype
        obj_display = tr_multi(
            "Tipita literal ({d})", "Typed literal ({d})", "Littéral typé ({d})",
        ).format(d=dtype)
        table.add_row(subj_label, pred_label, object_value)
        table.add_row(subj_id, predicate_id, obj_display)

        parts = [f"→ {dtype}"]
        if object_unit:
            try:
                unit_node = node_svc.resolve_node_id_prefix(object_unit)
            except AmbiguousUUIDError as e:
                warning(tr_multi("Ambigua unuo-prefikso: {e}", "Ambiguous unit prefix: {e}", "Préfixe unité ambigu : {e}").format(e=str(e)))
                return None, ""
            unit_label = resolve_node_label_from_node(unit_node) if unit_node else object_unit[:16]
            unit_id = unit_node["node_id"][:16] if unit_node else object_unit[:16]
            parts.append(f"unit: {unit_label} ({unit_id})")
        footnote = ", ".join(parts)
    else:
        # String literal
        quoted_val = f'"{object_value}"'
        table.add_row(subj_label, pred_label, quoted_val)
        table.add_row(subj_id, predicate_id, "")

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

    if table is None:
        return False

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
        f"{node_label} ({node_uuid[:16]})",
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
            raw_obj = arc["object"][:16]
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


# ── Node creation preview (no-arcs path) ────────────────────────────────


def build_node_preview_table(node_id: str, labels: dict[str, str], defns: dict[str, str]) -> Table:
    """Build a preview table showing node metadata before creation.

    Args:
        node_id: The node ID to display.
        labels: Language→label dict (already parsed, not JSON).
        defns: Language→definition dict (already parsed, not JSON).

    Returns:
        A Rich Table with node details.
    """
    table = Table(show_header=False, box=BOX_SIMPLE)
    table.add_column(tr_multi("Detaloj", "Detail", "Détail"), no_wrap=True)
    table.add_column("", no_wrap=True)

    table.add_row(tr_multi("ID", "ID", "ID"), node_id if node_id else tr_multi(
        "(aŭtomate generita)", "(auto-generated)", "(auto-généré)",
    ))

    if labels:
        labels_str = "\n".join(f"{lang}: {val}" for lang, val in labels.items())
        table.add_row(tr_multi("Etikedoj", "Labels", "Étiquettes"), labels_str)

    if defns:
        defns_str = "\n".join(f"{lang}: {val}" for lang, val in defns.items())
        table.add_row(tr_multi("Difinoj", "Definitions", "Définitions"), defns_str)

    return table


def build_node_modify_preview(
    node_id: str,
    old_labels: dict[str, str],
    new_labels: dict[str, str] | None,
    old_defns: dict[str, str],
    new_defns: dict[str, str] | None,
) -> Table | None:
    """Build a preview table showing old → new values for a node modifi.

    Only includes fields that actually changed.  Returns ``None`` if no
    fields changed (no-op).

    Args:
        node_id: Node ID.
        old_labels: Existing labels dict.
        new_labels: New labels dict, or ``None`` if not changing.
        old_defns: Existing definitions dict.
        new_defns: New definitions dict, or ``None`` if not changing.

    Returns:
        A Rich Table with old→new columns, or ``None`` if nothing changed.
    """
    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Kampo", "Field", "Champ"), no_wrap=True)
    table.add_column(tr_multi("Malnova", "Old", "Ancien"), no_wrap=True)
    table.add_column(tr_multi("Nova", "New", "Nouveau"), no_wrap=True)

    has_changes = False

    if new_labels is not None and new_labels != old_labels:
        has_changes = True
        old_lines = "\n".join(f"{k}: {v}" for k, v in sorted(old_labels.items())) if old_labels else "—"
        new_lines = "\n".join(f"{k}: {v}" for k, v in sorted(new_labels.items())) if new_labels else "—"
        table.add_row(
            tr_multi("Etikedoj", "Labels", "Étiquettes"),
            old_lines,
            new_lines,
        )

    if new_defns is not None and new_defns != old_defns:
        has_changes = True
        old_lines = "\n".join(f"{k}: {v}" for k, v in sorted(old_defns.items())) if old_defns else "—"
        new_lines = "\n".join(f"{k}: {v}" for k, v in sorted(new_defns.items())) if new_defns else "—"
        table.add_row(
            tr_multi("Difinoj", "Definitions", "Définitions"),
            old_lines,
            new_lines,
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
        labels: Language→label dict.
        defns: Language→definition dict.
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
            "Ĉu krei tiun nodon?",
            "Create this node?",
            "Créer ce nœud ?",
        ),
        default=True,
    )


# ── Predicate creation preview ──────────────────────────────────────────


def build_predicate_preview_table(pred_data: dict) -> Table:
    """Build a preview table showing predicate metadata before creation.

    Args:
        pred_data: Predicate data dict with keys:
            predicate_id, source, etikedoj (dict), priskriboj (dict).

    Returns:
        A Rich Table with predicate details.
    """
    table = Table(show_header=False, box=BOX_SIMPLE)
    table.add_column(tr_multi("Detaloj", "Detail", "Détail"), no_wrap=True)
    table.add_column("", no_wrap=True)

    pid = pred_data.get("predicate_id", "")
    table.add_row(tr_multi("ID", "ID", "ID"), pid)

    source = pred_data.get("source", "")
    if source:
        table.add_row(tr_multi("Fonto", "Source", "Source"), source)

    etikedoj = pred_data.get("etikedoj", {})
    if isinstance(etikedoj, dict) and etikedoj:
        labels_str = "\n".join(f"{lang}: {val}" for lang, val in etikedoj.items())
        table.add_row(tr_multi("Etikedoj", "Labels", "Étiquettes"), labels_str)

    priskriboj = pred_data.get("priskriboj", {})
    if isinstance(priskriboj, dict) and priskriboj:
        descs_str = "\n".join(f"{lang}: {val}" for lang, val in priskriboj.items())
        table.add_row(tr_multi("Priskriboj", "Descriptions", "Descriptions"), descs_str)

    return table


def build_predicate_modify_preview(
    pred_id: str,
    old_etikedoj: dict[str, str],
    new_etikedoj: dict[str, str] | None,
    old_priskriboj: dict[str, str],
    new_priskriboj: dict[str, str] | None,
) -> Table | None:
    """Build a preview table showing old → new values for a predicate modifi.

    Only includes fields that actually changed.  Returns ``None`` if no
    fields changed (no-op).

    Args:
        pred_id: Predicate ID (e.g. ``rdf:type``).
        old_etikedoj: Existing labels dict.
        new_etikedoj: New labels dict, or ``None`` if labels not changing.
        old_priskriboj: Existing descriptions dict.
        new_priskriboj: New descriptions dict, or ``None`` if not changing.

    Returns:
        A Rich Table with old→new columns, or ``None`` if nothing changed.
    """
    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Kampo", "Field", "Champ"), no_wrap=True)
    table.add_column(tr_multi("Malnova", "Old", "Ancien"), no_wrap=True)
    table.add_column(tr_multi("Nova", "New", "Nouveau"), no_wrap=True)

    has_changes = False

    # Labels (etikedoj)
    if new_etikedoj is not None and new_etikedoj != old_etikedoj:
        has_changes = True
        old_lines = "\n".join(f"{k}: {v}" for k, v in sorted(old_etikedoj.items())) if old_etikedoj else "—"
        new_lines = "\n".join(f"{k}: {v}" for k, v in sorted(new_etikedoj.items())) if new_etikedoj else "—"
        table.add_row(
            tr_multi("Etikedoj", "Labels", "Étiquettes"),
            old_lines,
            new_lines,
        )

    # Descriptions (priskriboj)
    if new_priskriboj is not None and new_priskriboj != old_priskriboj:
        has_changes = True
        old_lines = "\n".join(f"{k}: {v}" for k, v in sorted(old_priskriboj.items())) if old_priskriboj else "—"
        new_lines = "\n".join(f"{k}: {v}" for k, v in sorted(new_priskriboj.items())) if new_priskriboj else "—"
        table.add_row(
            tr_multi("Priskriboj", "Descriptions", "Descriptions"),
            old_lines,
            new_lines,
        )

    return table if has_changes else None


def confirm_predicate_creation(
    pred_data: dict,
    yes: bool = False,
) -> bool:
    """Show a confirmation prompt for creating a predicate.

    Displays a Rich table with predicate details, then asks for confirmation.

    Args:
        pred_data: Predicate data dict.
        yes: If True, skip confirmation.

    Returns:
        True if confirmed, False otherwise.
    """
    if yes:
        return True

    table = build_predicate_preview_table(pred_data)

    info("")
    info(table)

    pid = pred_data.get("predicate_id", "")
    return confirm_action(
        tr_multi(
            f"Ĉu krei predikaton {pid}?",
            f"Create predicate {pid}?",
            f"Créer le prédicat {pid}?",
        ),
        default=True,
    )
