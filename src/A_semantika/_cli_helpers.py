"""Shared CLI helpers: interactive picker, type flag validation, predicate
bootstrapping."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService

from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, tr_multi, warning
from A.utils.interactive import select_candidate
from A_semantika._node_service import AmbiguousUUIDError, NodeService
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika._triple_search import search_triples_by_labels
from A_semantika._triple_service import DuplicateTripleError, TripleService




# ── Deprecated alias resolution ───────────────────────────────────────


def resolve_deprecated(new_val: object, old_val: object,
                       old_name: str, new_name: str) -> object:
    """Resolve a CLI option renamed from *old_name* to *new_name*.

    If the user passed the old (deprecated) flag, warn and use its value.
    If both old and new are provided, raise an error.
    Returns the value to use (or *new_val* if neither is set).
    """
    if old_val is not None:
        if new_val is not None:
            from A import error as _err
            from A import tr_multi as _tr
            _err(_tr(
                f"Ne eblas uzi samtempe --{old_name} kaj --{new_name}",
                f"Cannot use both --{old_name} and --{new_name}",
                f"Impossible d'utiliser --{old_name} et --{new_name} à la fois",
            ))
            raise typer.Exit(1)
        from A import warning as _warn
        from A import tr_multi as _tr
        _warn(_tr(
            f"--{old_name} estas malrekomendita, uzu --{new_name}",
            f"--{old_name} is deprecated, use --{new_name}",
            f"--{old_name} est déprécié, utilisez --{new_name}",
        ))
        return old_val
    return new_val


def pick_triple(
    triple_svc: TripleService,
    node_svc: NodeService,
    pred_svc: PredicateService,
    subject: str | None = None,
    predicate: str | None = None,
    object: str | None = None,  # noqa: A002
) -> dict | None:
    """Show an interactive numbered picker for triples matching the given
    criteria (partial labels are resolved).  Returns the selected triple
    dict, or ``None`` if the user cancels or no matches exist.
    """
    results = search_triples_by_labels(
        triple_svc=triple_svc,
        node_svc=node_svc,
        pred_svc=pred_svc,
        subject=subject,
        predicate=predicate,
        object=object,
        limit=100,
    )
    if not results:
        error(tr_multi(
            "Neniuj kongruaj arkoj.",
            "No matching arcs found.",
            "Aucun arc correspondant trouvé.",
        ))
        return None

    result = select_candidate(
        results,
        columns=[
            {"header": tr_multi("Subjekto", "Subject", "Sujet")},
            {"header": tr_multi("Predikato", "Predicate", "Predicat")},
            {"header": tr_multi("Objekto", "Object", "Objet")},
            {"header": tr_multi("Tipo", "Type", "Type")},
        ],
        row_formatter=lambda t, i: [
            resolve_node_label(node_svc, t["subject_uuid"]),
            resolve_predicate_label(pred_svc, t["predicate_id"]),
            (
                resolve_node_label(node_svc, t["object_value"])
                if t["object_type"] == "uri"
                else t["object_value"]
            ),
            t["object_type"],
        ],
        prompt_text=tr_multi(
            "Elektu numeron de arko por forigi/modifi (aŭ Enter por nuligi)",
            "Select arc number to delete/modify (or Enter to cancel)",
            "Choisissez le numéro de l'arc à supprimer/modifier (ou Entrée pour annuler)",
        ),
    )
    if result is None:
        return None
    return result[1]  # The selected triple dict


def count_type_flags(str_: bool, int_: bool, float_: bool, bool_: bool) -> int:
    """Count how many type flags are set."""
    return sum([str_, int_, float_, bool_])


def validate_type_flags(
    str_: bool, int_: bool, float_: bool, bool_: bool,
    lingvo: str | None, unuo: str | None,
) -> str | None:
    """Validate type flag combinations. Returns datatype string or None for URI.

    Calls error() and raises typer.Exit(1) on invalid combinations.
    """
    count = count_type_flags(str_, int_, float_, bool_)
    if count > 1:
        error(
            tr_multi(
                "Ne eblas kombini --str, --int, --float, --bool",
                "Cannot combine --str, --int, --float, --bool",
                "Impossible de combiner --str, --int, --float, --bool",
            )
        )
        raise typer.Exit(1)
    if count == 0:
        if lingvo:
            error(
                tr_multi(
                    "--lingvo bezonas --str",
                    "--lingvo requires --str",
                    "--lingvo nécessite --str",
                )
            )
            raise typer.Exit(1)
        if unuo:
            error(
                tr_multi(
                    "--unuo bezonas --int aŭ --float",
                    "--unuo requires --int or --float",
                    "--unuo nécessite --int ou --float",
                )
            )
            raise typer.Exit(1)
        return None  # URI reference

    if str_:
        return None  # String literal, no datatype
    if int_:
        return "xsd:integer"
    if float_:
        return "xsd:decimal"
    if bool_:
        return "xsd:boolean"
    return None


def ensure_predicate(pred_svc: "PredicateService", predicate_id: str, label_eo: str) -> None:
    """Ensure a predicate exists, creating it if needed.

    Safe for concurrent operations: only ignores duplicate key errors,
    not other errors.
    """
    existing = pred_svc.get_by_predicate_id(predicate_id)
    if existing:
        return
    try:
        pred_svc.create({
            "predicate_id": predicate_id,
            "etikedoj": {"eo": label_eo},
            "source": "rdf",
        })
    except (ValueError, sqlite3.IntegrityError) as e:
        # Only ignore duplicate key errors (race condition from concurrent create)
        err_str = str(e)
        if "UNIQUE constraint failed" not in err_str and "already exists" not in err_str:
            raise


# ── Modify preview helpers ──────────────────────────────────────────────


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
    """Build a preview table for modifi showing old → new values.

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
            return f"{resolve_node_label(node_svc, val)} ({val[:16]})"
        if lang:
            return f'"{val}"@{lang}'
        return f'"{val}"'

    old_pred_label = resolve_predicate_label(pred_svc, predicate)
    old_obj_display = _obj_display(object_value, object_type, object_lang)
    table.add_row(
        tr_multi("Malnova", "Old", "Ancien"),
        f"{old_subj_label} ({subject_uuid[:16]})",
        old_pred_label,
        old_obj_display,
    )

    new_subj_label = resolve_node_label(node_svc, new_subj_uuid)
    new_pred_label = resolve_predicate_label(pred_svc, new_pred)
    new_obj_display = _obj_display(new_obj_value, new_obj_type, new_obj_lang)
    table.add_row(
        tr_multi("Nova", "New", "Nouveau"),
        f"{new_subj_label} ({new_subj_uuid[:16]})",
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
        1. Resolve ``object_raw`` as a node UUID prefix → check ``get_one()`` with ``object_type='uri'``
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
    (URI → literal → last-resort), then extracts type/lang metadata
    from the result.

    Returns:
        Tuple of (triple_dict or None, resolved_object_type, resolved_object_lang).
    """
    triple = _find_triple_by_spo(triple_svc, node_svc, subject_uuid, predicate, object)
    if triple is None:
        return None, "uri", None
    return triple, triple.get("object_type", "literal"), triple.get("object_lang")


# ── Arc resolution helpers (Issue #35/R12) ─────────────────────────────


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
        warning(tr_multi(
            "Arka celo ne trovita: {t} (preterlasita)",
            "Arc target not found: {t} (skipped)",
            "Cible d'arc non trouvée : {t} (ignorée)",
        ).format(t=user_input))
        return None

    _ARC_DEFS: list[tuple[str, str, str, str, str, str]] = [
        ("tipo", "rdf:type", "tipo", "type", "type",
         "Ambigua tipo-prefikso: {e}|Ambiguous type prefix: {e}|Préfixe type ambigu : {e}"),
        ("superklaso", "rdfs:subClassOf", "superklaso", "superclass", "superclasse",
         "Ambigua superklaso-prefikso: {e}|Ambiguous superclass prefix: {e}|Préfixe superclasse ambigu : {e}"),
        ("ne", "owl:disjointWith", "malakorda", "disjoint", "disjoint",
         "Ambigua malakorda-prefikso: {e}|Ambiguous disjoint prefix: {e}|Préfixe disjoint ambigu : {e}"),
        ("invers", "owl:inverseOf", "inversa", "inverse", "inverse",
         "Ambigua inversa-prefikso: {e}|Ambiguous inverse prefix: {e}|Préfixe inverse ambigu : {e}"),
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
                pass  # Silently skip — triple already exists, no harm
    except ValueError:
        # Rollback: remove already-created arcs first (FK constraint),
        # then delete the node to prevent orphan with partial arcs.
        # Wrap rollback in try/except so a rollback failure doesn't mask
        # the original ValueError that triggered it.
        try:
            triple_svc.remove_by_node(node_id_val)
            node_svc.delete(node_id_val)
        except (sqlite3.Error, ValueError) as rollback_err:
            warning(
                tr_multi(
                    "Enrulumbo malsukcesis por nodo {n}: {e}",
                    "Rollback failed for node {n}: {e}",
                    "Rétablissement échoué pour le nœud {n} : {e}",
                ).format(n=node_id_val, e=str(rollback_err))
            )
        raise
