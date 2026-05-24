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

from A import error, tr_multi
from A.utils.interactive import select_candidate
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika._triple_search import search_triples_by_labels




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
            from A import warning as _warn

            _warn(
                tr_multi(
                    "--lingvo ignorita sen --str",
                    "--lingvo ignored without --str",
                    "--lingvo ignoré sans --str",
                )
            )
        if unuo:
            from A import warning as _warn

            _warn(
                tr_multi(
                    "--unuo ignorita sen --int aŭ --float",
                    "--unuo ignored without --int or --float",
                    "--unuo ignoré sans --int ou --float",
                )
            )
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
