"""Predikato rubujo (trash) subcommand group: ls, restaurigi, malplenigi, forigi.

Provides CLI for managing soft-deleted predicates.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._predicate_service import _label_from_etikedoj
from A_semantika._rubujo_helpers import (
    batch_permanent_delete,
    batch_restore,
    build_trash_table,
)
from A_semantika.data.storage import get_db
from A_semantika.service import get_predicate_service

predikato_rubujo_app = typer.Typer(
    name="rubujo",
    help=tr_multi(
        "Administri forigitajn predikatojn (rubujon)",
        "Manage deleted predicates (trash)",
        "Gérer les prédicats supprimés (corbeille)",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


# ── Label helpers ────────────────────────────────────────────────────


def _get_predicate_label(pred: dict) -> str:
    """Get the display label for a predicate dict, from etikedoj JSON."""
    return _label_from_etikedoj(pred.get("etikedoj", "{}")) or pred.get("predicate_id", "")


# ── ls ───────────────────────────────────────────────────────────────


@predikato_rubujo_app.command("ls")
def ls(
    limit: int = typer.Option(
        50, "--limit", "-l",
        help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max"),
    ),
) -> None:
    """Listi predikatojn en la rubujo."""
    pred_svc = get_predicate_service()
    items = pred_svc.get_trash(limit=limit)

    if not items:
        info(tr_multi(
            "Rubujo de predikatoj estas malplena.",
            "Predicate trash is empty.",
            "La corbeille des prédicats est vide.",
        ))
        return

    table = build_trash_table(
        items, "predicate_id",
        tr_multi("Predikato ID", "Predicate ID", "ID prédicat"),
        tr_multi("Etikedo", "Label", "Étiquette"),
        tr_multi("Forigita", "Deleted", "Supprimé"),
        _get_predicate_label,
        show_full_id=True,
    )
    info(table)


# ── restaurigi ───────────────────────────────────────────────────────


@predikato_rubujo_app.command("restaurigi")
def restaurigi(
    predicate_ids: list[str] = typer.Argument(
        ...,
        help=tr_multi(
            "Predikato ID-oj (pluraj)",
            "Predicate IDs (multiple)",
            "IDs des prédicats (plusieurs)",
        ),
    ),
    yes: bool = typer.Option(
        False, "-y", "--jes", "--yes",
        help=tr_multi(
            "Preterpasi konfirmon",
            "Skip confirmation",
            "Ignorer la confirmation",
        ),
    ),
) -> None:
    """Restarigi predikatojn el la rubujo."""
    batch_restore(
        predicate_ids,
        get_predicate_service,
        get_db(),
        "predicates_rubujo",
        "predicate_id",
        label_getter=_get_predicate_label,
        yes=yes,
    )


# ── malplenigi ───────────────────────────────────────────────────────


@predikato_rubujo_app.command("malplenigi")
def malplenigi(
    days: Optional[int] = typer.Option(
        None, "--days", "-d",
        help=tr_multi(
            "Forigi nur rubon pli aĝan ol N tagoj",
            "Delete only trash older than N days",
            "Supprimer seulement la corbeille plus vieille que N jours",
        ),
    ),
    yes: bool = typer.Option(
        False, "-y", "--jes", "--yes",
        help=tr_multi(
            "Preterpasi konfirmon",
            "Skip confirmation",
            "Ignorer la confirmation",
        ),
    ),
) -> None:
    """Malplenigi la rubujon de predikatoj — permanente forigi.

    Warning: This operation is irreversible.
    """
    pred_svc = get_predicate_service()

    if days is not None:
        items = pred_svc.get_trash_older_than(days)
        if not items:
            info(tr_multi(
                "Neniuj predikatoj pli aĝaj ol {d} tagoj.",
                "No predicates older than {d} days.",
                "Aucun prédicat plus vieux que {d} jours.",
            ).format(d=days))
            return
    else:
        items = pred_svc.get_trash(limit=99999)
        if not items:
            info(tr_multi(
                "Rubujo de predikatoj estas jam malplena.",
                "Predicate trash is already empty.",
                "La corbeille des prédicats est déjà vide.",
            ))
            return

    if not yes:
        warning(tr_multi(
            "AVERTO: tiu ago estas necivilebla!",
            "WARNING: this action is irreversible!",
            "AVERTISSEMENT : cette action est irréversible !",
        ))

        table = build_trash_table(
            items, "predicate_id",
            tr_multi("Predikato ID", "Predicate ID", "ID prédicat"),
            tr_multi("Etikedo", "Label", "Étiquette"),
            tr_multi("Forigita", "Deleted", "Supprimé"),
            _get_predicate_label,
            show_full_id=True,
        )
        info(table)

        if not confirm_action(
            tr_multi(
                "Ĉu permanente forigi {n} predikatojn el la rubujo?",
                "Permanently delete {n} predicates from trash?",
                "Supprimer définitivement {n} prédicats de la corbeille?",
            ).format(n=len(items)),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    if days is not None:
        deleted_count = pred_svc.empty_trash(days=days)
    else:
        deleted_count = pred_svc.empty_all_trash()

    info(tr_multi(
        "Rubujo de predikatoj malplenigita: {n} forigitaj.",
        "Predicate trash emptied: {n} deleted.",
        "Corbeille des prédicats vidée : {n} supprimés.",
    ).format(n=deleted_count))


# ── forigi (permanent delete from trash) ─────────────────────────────


@predikato_rubujo_app.command("forigi")
def forigi(
    predicate_ids: list[str] = typer.Argument(
        ...,
        help=tr_multi(
            "Predikato ID-oj por permanenta forigo (pluraj)",
            "Predicate IDs for permanent deletion (multiple)",
            "IDs des prédicats pour suppression définitive (plusieurs)",
        ),
    ),
    yes: bool = typer.Option(
        False, "-y", "--jes", "--yes",
        help=tr_multi(
            "Preterpasi konfirmon",
            "Skip confirmation",
            "Ignorer la confirmation",
        ),
    ),
) -> None:
    """Permanente forigi predikatojn el rubujo."""
    batch_permanent_delete(
        predicate_ids,
        get_predicate_service,
        get_db(),
        "predicates_rubujo",
        "predicate_id",
        label_getter=_get_predicate_label,
        yes=yes,
    )
