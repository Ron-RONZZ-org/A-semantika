"""Interactive triple picker and shared resolve_triple() helper.

Extracted from _cli_helpers.py to keep files under 500 lines.
Provides single and multi-select triple pickers, plus the shared
resolve_triple() that unifies modifi/forigi/provo resolution logic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, tr_multi
from A.utils.interactive import select_candidate, select_candidates
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika._preview_triple import format_tipo
from A_semantika._triple_search import search_triples_by_labels

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService


# ── Shared columns / row formatter ────────────────────────────────────

_TRIPLE_COLUMNS = [
    {"header": tr_multi("Subjekto", "Subject", "Sujet")},
    {"header": tr_multi("Predikato", "Predicate", "Predicat")},
    {"header": tr_multi("Objekto", "Object", "Objet")},
    {"header": tr_multi("Tipo", "Type", "Type")},
]


def _format_triple_row(
    node_svc: NodeService,
    pred_svc: PredicateService,
    triple: dict,
) -> list[str]:
    """Format a triple dict into display strings for the picker table."""
    return [
        resolve_node_label(node_svc, triple["subject_uuid"]),
        resolve_predicate_label(pred_svc, triple["predicate_id"]),
        (
            resolve_node_label(node_svc, triple["object_value"])
            if triple.get("object_type") == "uri"
            else triple["object_value"]
        ),
        format_tipo(
            triple.get("object_type", "uri"),
            triple.get("object_datatype"),
            triple.get("object_lang"),
        ),
    ]


# ── resolve_triple: unified resolution (Issue #97) ─────────────────────


def resolve_triple(
    node_svc: NodeService,
    pred_svc: PredicateService,
    triple_svc: TripleService,
    subject: str | None = None,
    predicate: str | None = None,
    object: str | None = None,  # noqa: A002
) -> dict | None:
    """Resolve a triple by partial label matching.

    Converts empty-string wildcards to ``None`` (no constraint on that
    field).  Returns the triple directly if exactly one match is found,
    shows an interactive picker if multiple matches, and returns ``None``
    if no matches or the user cancels.

    This is the shared helper used by ``modifi``, ``forigi``, and
    ``provo`` for unified resolution logic (Issue #97).

    Args:
        node_svc: NodeService instance.
        pred_svc: PredicateService instance.
        triple_svc: TripleService instance.
        subject: Subject label / UUID prefix / ``""`` for wildcard.
        predicate: Predicate label / ID / ``""`` for wildcard.
        object: Object label / literal / ``""`` for wildcard.

    Returns:
        A triple dict with keys: ``subject_uuid``, ``predicate_id``,
        ``object_value``, ``object_type``, ``object_lang``, etc.
        ``None`` if not found or cancelled.
    """
    # Convert empty-string wildcards to None (no constraint)
    subj = subject if subject else None
    pred = predicate if predicate else None
    obj = object if object else None

    results = search_triples_by_labels(
        triple_svc=triple_svc,
        node_svc=node_svc,
        pred_svc=pred_svc,
        subject=subj,
        predicate=pred,
        object=obj,
        limit=100,
    )

    if not results:
        error(tr_multi(
            "Neniuj kongruaj arkoj.",
            "No matching arcs found.",
            "Aucun arc correspondant trouvé.",
        ))
        return None

    if len(results) == 1:
        return results[0]

    return _do_pick_triple(node_svc, pred_svc, results)


# ── Single-select picker ───────────────────────────────────────────────


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

    return _do_pick_triple(node_svc, pred_svc, results)


def _do_pick_triple(
    node_svc: NodeService,
    pred_svc: PredicateService,
    results: list[dict],
) -> dict | None:
    """Internal: show a picker for exactly one triple from *results*."""
    result = select_candidate(
        results,
        columns=_TRIPLE_COLUMNS,
        row_formatter=lambda t, i: _format_triple_row(node_svc, pred_svc, t),
        prompt_text=tr_multi(
            "Elektu numeron de arko por forigi/modifi (aŭ Enter por nuligi)",
            "Select arc number to delete/modify (or Enter to cancel)",
            "Choisissez le numéro de l'arc à supprimer/modifier (ou Entrée pour annuler)",
        ),
    )
    if result is None:
        return None
    return result[1]


# ── Multi-select picker ────────────────────────────────────────────────


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
        columns=_TRIPLE_COLUMNS,
        row_formatter=lambda t, i: _format_triple_row(node_svc, pred_svc, t),
        prompt_text=tr_multi(
            "Elektu arko-numerojn por forigi (spacigitaj, aŭ Enter por nuligi)",
            "Select arc numbers to delete (space-separated, or Enter to cancel)",
            "Choisissez les numéros d'arcs à supprimer (séparés par des espaces, ou Entrée pour annuler)",
        ),
    )
    if selections is None:
        return None
    return [item for _, item in selections]
