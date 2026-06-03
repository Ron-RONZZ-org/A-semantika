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
from A.utils.interactive import select_candidate, select_candidates
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError, NodeService
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika._preview_triple import format_tipo
from A_semantika._triple_search import search_triples_by_labels
from A_semantika._triple_service import DuplicateTripleError, TripleService
from A_semantika.data.storage import KATEX_DATATYPE


# -- Language-to-MIME mapping for code block literals ------------------

LANG_TO_MIME: dict[str, str] = {
    "python": "text/x-python",
    "javascript": "text/javascript",
    "typescript": "text/typescript",
    "java": "text/x-java",
    "html": "text/html",
    "css": "text/css",
    "bash": "text/x-bash",
    "sh": "text/x-sh",
    "sql": "text/x-sql",
    "yaml": "text/x-yaml",
    "yml": "text/x-yaml",
    "json": "application/json",
    "xml": "application/xml",
    "rust": "text/x-rust",
    "go": "text/x-go",
    "c": "text/x-csrc",
    "cpp": "text/x-c++src",
    "c++": "text/x-c++src",
    "ruby": "text/x-ruby",
    "php": "text/x-php",
    "swift": "text/x-swift",
    "kotlin": "text/x-kotlin",
    "scala": "text/x-scala",
    "r": "text/x-r",
    "lua": "text/x-lua",
    "perl": "text/x-perl",
    "haskell": "text/x-haskell",
    "clojure": "text/x-clojure",
    "elixir": "text/x-elixir",
    "erlang": "text/x-erlang",
    "dart": "text/x-dart",
    "groovy": "text/x-groovy",
    "matlab": "text/x-matlab",
    "diff": "text/x-diff",
    "qd": "text/x-quarkdown",
    "tex": "text/x-tex",
    "latex": "text/x-tex",
    "makefile": "text/x-makefile",
    "dockerfile": "text/x-dockerfile",
    "plain": "text/plain",
    "text": "text/plain",
}


# ── Ambiguous prefix → interactive selection ──────────────────────────


def _prompt_select_ambiguous_predicate(
    pred_svc: "PredicateService",
    matches: list[dict],
) -> dict | None:
    """Show an interactive numbered picker for ambiguous predicate prefixes.

    Args:
        pred_svc: PredicateService instance.
        matches: List of matching predicate dicts.

    Returns:
        Selected predicate dict, or ``None`` if cancelled.
    """
    from A_semantika._preview import resolve_predicate_label

    result = select_candidate(
        matches,
        columns=[
            {"header": tr_multi("ID", "ID", "ID")},
            {"header": tr_multi("Etikedo", "Label", "Étiquette")},
        ],
        row_formatter=lambda m, i: [
            m["predicate_id"],
            resolve_predicate_label(pred_svc, m["predicate_id"]),
        ],
        prompt_text=tr_multi(
            "Elektu predikaton (aŭ Enter por nuligi)",
            "Select predicate (or Enter to cancel)",
            "Choisissez un prédicat (ou Entrée pour annuler)",
        ),
    )
    if result is None:
        return None
    return result[1]


def _prompt_select_ambiguous_node(
    node_svc: "NodeService",
    matches: list[dict],
) -> dict | None:
    """Show an interactive numbered picker for ambiguous node ID prefixes.

    Args:
        node_svc: NodeService instance.
        matches: List of matching node dicts.

    Returns:
        Selected node dict, or ``None`` if cancelled.
    """
    from A_semantika._preview import resolve_node_label

    result = select_candidate(
        matches,
        columns=[
            {"header": tr_multi("ID", "ID", "ID")},
            {"header": tr_multi("Etikedo", "Label", "Étiquette")},
        ],
        row_formatter=lambda m, i: [
            m["node_id"],
            resolve_node_label(node_svc, m["node_id"]),
        ],
        prompt_text=tr_multi(
            "Elektu nodon (aŭ Enter por nuligi)",
            "Select node (or Enter to cancel)",
            "Choisissez un nœud (ou Entrée pour annuler)",
        ),
    )
    if result is None:
        return None
    return result[1]


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
            error(tr_multi(
                f"Ne eblas uzi samtempe --{old_name} kaj --{new_name}",
                f"Cannot use both --{old_name} and --{new_name}",
                f"Impossible d'utiliser --{old_name} et --{new_name} à la fois",
            ))
            raise typer.Exit(1)
        warning(tr_multi(
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
            format_tipo(
                t.get("object_type", "uri"),
                t.get("object_datatype"),
                t.get("object_lang"),
            ),
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


def pick_triples(
    triple_svc: TripleService,
    node_svc: NodeService,
    pred_svc: PredicateService,
    subject: str | None = None,
    predicate: str | None = None,
    object: str | None = None,  # noqa: A002
) -> list[dict] | None:
    """Show an interactive multi-select picker for triples.

    Same search semantics as :func:`pick_triple`, but the user may enter
    space-separated numbers to select multiple arcs at once.

    Returns:
        List of selected triple dicts, or ``None`` if cancelled / no matches.
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

    selections = select_candidates(
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
            format_tipo(
                t.get("object_type", "uri"),
                t.get("object_datatype"),
                t.get("object_lang"),
            ),
        ],
        prompt_text=tr_multi(
            "Elektu arko-numerojn por forigi (spacigitaj, aŭ Enter por nuligi)",
            "Select arc numbers to delete (space-separated, or Enter to cancel)",
            "Choisissez les numéros d'arcs à supprimer (séparés par des espaces, ou Entrée pour annuler)",
        ),
    )
    if selections is None:
        return None
    return [item for _, item in selections]


def count_type_flags(
    str_: bool, int_: bool, float_: bool, bool_: bool,
    katex: bool = False, kodbloko: bool = False,
) -> int:
    """Count how many type flags are set."""
    return sum([str_, int_, float_, bool_, katex, kodbloko])


def validate_type_flags(
    str_: bool, int_: bool, float_: bool, bool_: bool,
    lingvo: str | None, unuo: str | None,
    katex: bool = False, kodbloko: bool = False, kodlingvo: str | None = None,
) -> tuple[str | None, str]:
    """Validate type flag combinations.

    Supports plain string (--str), numeric (--int/--float/--bool),
    KaTeX formula (--katex), and code block (--kodbloko) literals.

    Returns:
        Tuple of (datatype, object_type):
        - datatype: ``None`` for URI/string, ``"xsd:integer"``, etc.
          For KaTeX: returns ``KATEX_DATATYPE`` constant.
          For code block: returns MIME type from ``LANG_TO_MIME`` dict.
        - object_type: ``"uri"`` or ``"literal"``

    Calls error() and raises typer.Exit(1) on invalid combinations.
    """
    count = count_type_flags(str_, int_, float_, bool_, katex=katex, kodbloko=kodbloko)
    if count > 1:
        error(
            tr_multi(
                "Ne eblas kombini tipajn flagojn (--str, --int, --float, --bool, --katex, --kodbloko)",
                "Cannot combine type flags (--str, --int, --float, --bool, --katex, --kodbloko)",
                "Impossible de combiner les indicateurs de type (--str, --int, --float, --bool, --katex, --kodbloko)",
            )
        )
        raise typer.Exit(1)

    # kodlingvo requires kodbloko
    if kodlingvo and not kodbloko:
        error(tr_multi(
            "--kodlingvo bezonas --kodbloko",
            "--kodlingvo requires --kodbloko",
            "--kodlingvo nécessite --kodbloko",
        ))
        raise typer.Exit(1)

    if count == 0:
        if lingvo:
            error(
                tr_multi(
                    "--lingvo bezonas --str aŭ --str-dosiero",
                    "--lingvo requires --str or --str-dosiero",
                    "--lingvo nécessite --str ou --str-dosiero",
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
        return (None, "uri")  # URI reference

    if katex:
        return (KATEX_DATATYPE, "literal")
    if kodbloko:
        mime = LANG_TO_MIME.get(kodlingvo, "text/plain") if kodlingvo else "text/plain"
        return (mime, "literal")
    if str_:
        return (None, "literal")  # String literal, no datatype
    if int_:
        return ("xsd:integer", "literal")
    if float_:
        return ("xsd:decimal", "literal")
    if bool_:
        return ("xsd:boolean", "literal")
    return (None, "uri")


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

    .. deprecated::
       Use :func:`A_semantika._cli_modify_preview.build_modify_preview` instead.

    Handles both URI and literal object types.
    """
    from A_semantika._cli_modify_preview import build_modify_preview as _build
    return _build(
        node_svc, pred_svc,
        subject_uuid, predicate, object_value, object_type, object_lang,
        new_subj_uuid, new_pred, new_obj_value, new_obj_type, new_obj_lang,
    )


def _find_triple_by_spo(
    triple_svc, node_svc, subject_uuid: str, predicate: str, object_raw: str,
) -> dict | None:
    """Find an existing triple by subject/predicate/object, trying URI then literal.

    .. deprecated::
       Use :func:`A_semantika._cli_modify_preview._find_triple_by_spo` instead.

    """
    from A_semantika._cli_modify_preview import _find_triple_by_spo as _find
    return _find(triple_svc, node_svc, subject_uuid, predicate, object_raw)


def find_triple_direct(
    triple_svc, node_svc, subject_uuid: str, predicate: str, object: str,
) -> tuple[dict | None, str, str | None]:
    """Find an existing triple in direct mode (full SPO specified).

    .. deprecated::
       Use :func:`A_semantika._cli_modify_preview.find_triple_direct` instead.

    """
    from A_semantika._cli_modify_preview import find_triple_direct as _find
    return _find(triple_svc, node_svc, subject_uuid, predicate, object)


# ── Arc resolution helpers (Issue #35/R12) ─────────────────────────────

def resolve_arc_targets(
    node_svc: NodeService,
    tipo: list[str] | None,
    superklaso: list[str] | None,
    ne: list[str] | None,
    invers: list[str] | None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Resolve arc target node IDs from CLI shortcut flags.

    .. deprecated::
       Use :func:`A_semantika._cli_arc_helpers.resolve_arc_targets` instead.

    """
    from A_semantika._cli_arc_helpers import resolve_arc_targets as _resolve
    return _resolve(node_svc, tipo, superklaso, ne, invers)


def create_node_arcs(
    triple_svc: TripleService,
    node_svc: NodeService,
    node_id_val: str,
    arcs: list[dict],
) -> None:
    """Create arcs for a node, rolling back on failure.

    .. deprecated::
       Use :func:`A_semantika._cli_arc_helpers.create_node_arcs` instead.

    """
    from A_semantika._cli_arc_helpers import create_node_arcs as _create
    return _create(triple_svc, node_svc, node_id_val, arcs)
