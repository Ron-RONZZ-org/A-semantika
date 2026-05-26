"""Predikato rubujo (trash) subcommand group: ls, restaurigi, malplenigi, forigi.

Provides CLI for managing soft-deleted predicates.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A_semantika._predicate_service import _label_from_etikedoj
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


# ── Shared helpers ──────────────────────────────────────────────────


def _get_predicate_label(pred: dict) -> str:
    """Get the display label for a predicate dict, from etikedoj JSON."""
    return _label_from_etikedoj(pred.get("etikedoj", "{}")) or pred.get("predicate_id", "")


def _resolve_trash_predicate(predicate_id: str) -> dict | None:
    """Resolve a predicate_id against the trash table (predicates_rubujo)."""
    pred_svc = get_predicate_service()

    # Full match first (case-insensitive)
    entry = pred_svc.db.execute_one(
        "SELECT * FROM predicates_rubujo WHERE predicate_id = ? COLLATE NOCASE",
        (predicate_id,),
    )
    if entry:
        return entry

    # Prefix match (LIKE + COLLATE NOCASE)
    escaped = predicate_id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    entries = pred_svc.db.execute(
        "SELECT * FROM predicates_rubujo WHERE predicate_id LIKE ? COLLATE NOCASE ESCAPE '\\'",
        (f"{escaped}%",),
    )
    if not entries:
        return None
    if len(entries) > 1:
        msg = f"Predicate ID prefix '{predicate_id}' is ambiguous ({len(entries)} matches)"
        raise ValueError(msg)
    return entries[0]


def _batch_resolve_trash_predicates(
    predicate_ids: list[str],
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Resolve multiple predicate_id prefixes against the trash table.

    Returns (resolved_predicates, errors) where errors is a list of
    (input, reason) tuples for unresolvable IDs.
    """
    resolved: list[dict] = []
    errors: list[tuple[str, str]] = []

    for pid in predicate_ids:
        try:
            pred = _resolve_trash_predicate(pid)
            if pred:
                resolved.append(pred)
            else:
                errors.append((pid, tr_multi(
                    "ne trovita en rubujo",
                    "not found in trash",
                    "non trouvé dans la corbeille",
                )))
        except ValueError as e:
            errors.append((pid, tr_multi(
                "ambigua prefikso: {e}",
                "ambiguous prefix: {e}",
                "préfixe ambigu : {e}",
            ).format(e=str(e))))

    return resolved, errors


# ── ls ─────────────────────────────────────────────────────────────


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

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Predikato ID", "Predicate ID", "ID prédicat"), no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)
    table.add_column(tr_multi("Forigita", "Deleted", "Supprimé"), no_wrap=True)

    for n in items:
        label = _get_predicate_label(n)
        deleted_at = (n.get("forigita_je") or "?")[:19]
        table.add_row(n["predicate_id"], label, deleted_at)

    info(table)


# ── restaurigi ─────────────────────────────────────────────────────


def _batch_restore(predicate_ids: list[str], yes: bool) -> None:
    """Shared batch-restore logic."""
    pred_svc = get_predicate_service()

    resolved, errors = _batch_resolve_trash_predicates(predicate_ids)

    for input_val, reason in errors:
        error(tr_multi(
            "Restarigi {i}: {r}",
            "Restore {i}: {r}",
            "Restaurer {i} : {r}",
        ).format(i=input_val, r=reason))

    if not resolved:
        error(tr_multi(
            "Nenio restaŭrebla.",
            "Nothing to restore.",
            "Rien à restaurer.",
        ))
        raise typer.Exit(1)

    if not yes and len(resolved) >= 2:
        from A.utils.interactive import confirm_action

        label_list = ", ".join(
            _get_predicate_label(n) or n["predicate_id"]
            for n in resolved
        )
        if not confirm_action(
            tr_multi(
                "Ĉu restarigi {n} predikatojn: {labels}?",
                "Restore {n} predicates: {labels}?",
                "Restaurer {n} prédicats : {labels}?",
            ).format(n=len(resolved), labels=label_list),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    restored = 0
    for pred in resolved:
        try:
            result = pred_svc.restore(pred["predicate_id"])
            if result:
                restored += 1
                info(tr_multi(
                    "Restarigita: {p}",
                    "Restored: {p}",
                    "Restauré : {p}",
                ).format(p=pred["predicate_id"]))
        except (sqlite3.Error, ValueError) as e:
            error(tr_multi(
                "Eraro restarigante {p}: {e}",
                "Error restoring {p}: {e}",
                "Erreur lors de la restauration de {p} : {e}",
            ).format(p=pred["predicate_id"], e=str(e)))

    info(tr_multi(
        "Restarigis {r} el {t} predikatojn.",
        "Restored {r} of {t} predicates.",
        "Restauré {r} sur {t} prédicats.",
    ).format(r=restored, t=len(resolved)))


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
    _batch_restore(predicate_ids, yes)


# ── malplenigi ─────────────────────────────────────────────────────


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

        table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
        table.add_column(tr_multi("Predikato ID", "Predicate ID", "ID prédicat"), no_wrap=True)
        table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)
        table.add_column(tr_multi("Forigita", "Deleted", "Supprimé"), no_wrap=True)

        for n in items:
            label = _get_predicate_label(n)
            deleted_at = n.get("forigita_je", "")[:19]
            table.add_row(n["predicate_id"], label, deleted_at)

        info(table)

        from A.utils.interactive import confirm_action

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


# ── forigi (permanent delete from trash) ───────────────────────────


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
    pred_svc = get_predicate_service()

    resolved, errors = _batch_resolve_trash_predicates(predicate_ids)

    for input_val, reason in errors:
        error(tr_multi(
            "Forigi {i}: {r}",
            "Delete {i}: {r}",
            "Supprimer {i} : {r}",
        ).format(i=input_val, r=reason))

    if not resolved:
        error(tr_multi(
            "Nenio forigebla el rubujo de predikatoj.",
            "Nothing to delete from predicate trash.",
            "Rien à supprimer de la corbeille des prédicats.",
        ))
        raise typer.Exit(1)

    if not yes and len(resolved) >= 2:
        table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
        table.add_column(tr_multi("Predikato ID", "Predicate ID", "ID prédicat"), no_wrap=True)
        table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)
        table.add_column(tr_multi("Forigita", "Deleted", "Supprimé"), no_wrap=True)

        for n in resolved:
            label = _get_predicate_label(n)
            deleted_at = n.get("forigita_je", "")[:19]
            table.add_row(n["predicate_id"], label, deleted_at)

        info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu permanente forigi {n} predikatojn el la rubujo?",
                "Permanently delete {n} predicates from trash?",
                "Supprimer définitivement {n} prédicats de la corbeille?",
            ).format(n=len(resolved)),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    deleted = 0
    for pred in resolved:
        try:
            pred_svc.permanent_delete(pred["predicate_id"])
            deleted += 1
            info(tr_multi(
                "Permanente forigita: {p}",
                "Permanently deleted: {p}",
                "Définitivement supprimé : {p}",
            ).format(p=pred["predicate_id"]))
        except (sqlite3.Error, ValueError) as e:
            error(tr_multi(
                "Eraro forigante {p}: {e}",
                "Error deleting {p}: {e}",
                "Erreur lors de la suppression de {p} : {e}",
            ).format(p=pred["predicate_id"], e=str(e)))

    info(tr_multi(
        "Permanente forigis {d} el {t} predikatojn.",
        "Permanently deleted {d} of {t} predicates.",
        "Définitivement supprimé {d} sur {t} prédicats.",
    ).format(d=deleted, t=len(resolved)))
