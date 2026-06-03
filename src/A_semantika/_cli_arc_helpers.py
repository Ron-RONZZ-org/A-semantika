"""Arc resolution and creation helpers extracted from _cli_helpers.py.

Contains resolve_arc_targets and create_node_arcs.
"""
from __future__ import annotations

import sqlite3

from A import error, info, tr_multi, warning
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError, NodeService
from A_semantika._preview import resolve_predicate_label
from A_semantika._triple_service import DuplicateTripleError, TripleService
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table


# ---- Arc resolution helpers (Issue #35/R12) -----------------------------


def resolve_arc_targets(
    node_svc: NodeService,
    tipo: list[str] | None,
    superklaso: list[str] | None,
    ne: list[str] | None,
    invers: list[str] | None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Resolve arc target node IDs from CLI shortcut flags.

    Returns (arc_templates, errors) where each template is
    (target_node_id, predicate_id). Invalid/ambiguous inputs
    produce error messages instead of creating arcs.
    """
    arc_templates: list[tuple[str, str]] = []
    arc_errors: list[str] = []

    def _resolve_one(predicate: str, user_input: str) -> str | None:
        target = node_svc.resolve_node_id_prefix(user_input)
        if target:
            return target["node_id"]
        # Fallback: substring match
        try:
            target = node_svc.resolve_node_id_substring(user_input)
        except AmbiguousUUIDError:
            warning(tr_multi(
                "Ambigua arka celo: {t} (preterlasita)",
                "Ambiguous arc target: {t} (skipped)",
                "Cible d'arc ambiguë : {t} (ignoree)",
            ).format(t=user_input))
            return None
        if target:
            return target["node_id"]
        warning(tr_multi(
            "Arka celo ne trovita: {t} (preterlasita)",
            "Arc target not found: {t} (skipped)",
            "Cible d'arc non trouvee : {t} (ignoree)",
        ).format(t=user_input))
        return None

    _ARC_DEFS: list[tuple[str, str, str, str, str, str]] = [
        ("tipo", "rdf:type", "tipo", "type", "type",
         "Ambigua tipo-prefikso: {e}|Ambiguous type prefix: {e}|Prefixe type ambigu : {e}"),
        ("superklaso", "rdfs:subClassOf", "superklaso", "superclass", "superclasse",
         "Ambigua superklaso-prefikso: {e}|Ambiguous superclass prefix: {e}|Prefixe superclasse ambigu : {e}"),
        ("ne", "owl:disjointWith", "malakorda", "disjoint", "disjoint",
         "Ambigua malakorda-prefikso: {e}|Ambiguous disjoint prefix: {e}|Prefixe disjoint ambigu : {e}"),
        ("invers", "owl:inverseOf", "inversa", "inverse", "inverse",
         "Ambigua inversa-prefikso: {e}|Ambiguous inverse prefix: {e}|Prefixe inverse ambigu : {e}"),
    ]

    inputs_map = {
        "tipo": tipo,
        "superklaso": superklaso,
        "ne": ne,
        "invers": invers,
    }

    for key, predicate, _eo_label, _en_label, _fr_label, err_tmpl in _ARC_DEFS:
        inputs = inputs_map.get(key) or []
        for val in inputs:
            try:
                target_id = _resolve_one(predicate, val)
                if target_id:
                    arc_templates.append((target_id, predicate))
            except AmbiguousUUIDError as e:
                parts = err_tmpl.split("|")
                arc_errors.append(tr_multi(parts[0], parts[1], parts[2]).format(e=str(e)))

    return arc_templates, arc_errors


def create_node_arcs(
    triple_svc: TripleService,
    node_svc: NodeService,
    node_id_val: str,
    arcs: list[dict],
) -> None:
    """Create arcs for a node, rolling back on failure.

    This ensures atomicity: either all arcs are created, or any
    already-created arcs and the node are removed so no orphan node
    with partial arcs remains.

    The rollback first deletes arcs referencing ``node_id_val`` (FK
    constraint), then soft-deletes the node.
    """
    try:
        for arc in arcs:
            try:
                triple_svc.add(
                    subject_uuid=arc["subject"],
                    predicate_id=arc["predicate"],
                    object_value=arc["object"],
                    object_type=arc["object_type"],
                )
            except DuplicateTripleError:
                pass  # Silently skip triple already exists, no harm
    except ValueError:
        # Rollback: remove already-created arcs first (FK constraint),
        # then hard-delete the node to prevent orphan with partial arcs
        # (soft-delete would leave a trash entry, which is misleading
        # since the node was never successfully created).
        # Wrap rollback in try/except so a rollback failure does not mask
        # the original ValueError that triggered it.
        try:
            triple_svc.remove_by_node(node_id_val)
            node_svc.delete(node_id_val, soft=False)
        except (sqlite3.Error, ValueError) as rollback_err:
            warning(
                tr_multi(
                    "Enrulumbo malsukcesis por nodo {n}: {e}",
                    "Rollback failed for node {n}: {e}",
                    "Retablissement echoue pour le nud {n} : {e}",
                ).format(n=node_id_val, e=str(rollback_err))
            )
        raise
