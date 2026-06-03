"""Modify preview helpers extracted from _cli_helpers.py.

Contains build_modify_preview, _find_triple_by_spo, find_triple_direct.
"""
from __future__ import annotations

from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import tr_multi


def build_modify_preview(
    node_svc,
    pred_svc,
    subject_uuid: str,
    predicate: str,
    object_value: str,
    object_type: str,
    object_lang: str | None,
    new_subj_uuid: str,
    new_pred: str,
    new_obj_value: str,
    new_obj_type: str,
    new_obj_lang: str | None,
) -> Table:
    """Build a preview table for modifi showing old rightarrow new values.

    Handles both URI and literal object types.
    """
    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("", no_wrap=True)
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=True)

    old_subj_label = resolve_node_label(node_svc, subject_uuid)

    def _obj_display(val: str, typ: str, lang: str | None) -> str:
        if typ == "uri":
            return f"{resolve_node_label(node_svc, val)} ({truncate_uuid(val)})"
        if lang:
            return f'"{val}"@{lang}'
        return f'"{val}"'

    old_pred_label = resolve_predicate_label(pred_svc, predicate)
    old_obj_display = _obj_display(object_value, object_type, object_lang)
    table.add_row(
        tr_multi("Malnova", "Old", "Ancien"),
        f"{old_subj_label} ({truncate_uuid(subject_uuid)})",
        old_pred_label,
        old_obj_display,
    )

    new_subj_label = resolve_node_label(node_svc, new_subj_uuid)
    new_pred_label = resolve_predicate_label(pred_svc, new_pred)
    new_obj_display = _obj_display(new_obj_value, new_obj_type, new_obj_lang)
    table.add_row(
        tr_multi("Nova", "New", "Nouveau"),
        f"{new_subj_label} ({truncate_uuid(new_subj_uuid)})",
        new_pred_label,
        new_obj_display,
    )

    return table


def _find_triple_by_spo(
    triple_svc, node_svc, subject_uuid: str, predicate: str, object_raw: str,
) -> dict | None:
    """Find an existing triple by subject/predicate/object, trying URI then literal.

    Shared helper used by both ``find_triple_direct()`` (for ``modifi``) and
    ``_find_triple_for_delete()`` (for ``forigi``), consolidating the >80%
    shared lookup logic.

    Resolution order:
        1. Resolve ``object_raw`` as a node UUID prefix check ``get_one()`` with ``object_type='uri'``
        2. Search triples by literal match (subject + predicate + raw string)
        3. Last resort: search by resolved node ID regardless of type

    Returns:
        The matched triple dict, or ``None`` if no match found.
    """
    # Try URI: resolve object as node
    try:
        obj_node = node_svc.resolve_node_id_prefix(object_raw)
    except AmbiguousUUIDError:
        obj_node = None

    if obj_node:
        existing = triple_svc.get_one(subject_uuid, predicate, obj_node["node_id"], "uri")
        if existing:
            return existing

    # Try literal match by subject + predicate + object_value
    results = triple_svc.search_triples(
        subject_uuids=[subject_uuid],
        predicate_ids=[predicate],
        object_values=[object_raw],
        limit=2,
    )
    if results:
        return results[0]

    # Last resort: try with raw object as URI (for object that matched UUID
    # but was not a triple with object_type='uri')
    if obj_node:
        results = triple_svc.search_triples(
            subject_uuids=[subject_uuid],
            predicate_ids=[predicate],
            object_values=[obj_node["node_id"]],
            limit=2,
        )
        if results:
            return results[0]

    return None


def find_triple_direct(
    triple_svc, node_svc, subject_uuid: str, predicate: str, object: str,
) -> tuple[dict | None, str, str | None]:
    """Find an existing triple in direct mode (full SPO specified).

    Delegates to ``_find_triple_by_spo()`` for the core lookup logic
    (URI rightarrow literal rightarrow last-resort), then extracts type/lang metadata
    from the result.

    Returns:
        Tuple of (triple_dict or None, resolved_object_type, resolved_object_lang).
    """
    triple = _find_triple_by_spo(triple_svc, node_svc, subject_uuid, predicate, object)
    if triple is None:
        return None, "uri", None
    return triple, triple.get("object_type", "literal"), triple.get("object_lang")
