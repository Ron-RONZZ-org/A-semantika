"""Rubujo (trash) subcommand group: ls, restaurigi, malplenigi, forigi.

Provides CLI for managing soft-deleted nodes.
restaurigi accepts multiple positional args. The old accented aliases
restaŭrigi and restauxrigi are kept as hidden deprecated aliases.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._rubujo_helpers import (
    batch_permanent_delete,
    batch_restore,
    build_trash_table,
    get_label_from_etikedoj,
)
from A_semantika.data.storage import get_db
from A_semantika.service import get_node_service

rubujo_app = typer.Typer(
    name="rubujo",
    help=tr_multi(
        "Administri forigitajn nodojn (rubujon)",
        "Manage deleted nodes (trash)",
        "Gérer les nœuds supprimés (corbeille)",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


@rubujo_app.command("ls")
def ls(
    limit: int = typer.Option(
        50, "--limit", "-l",
        help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max"),
    ),
) -> None:
    """Listi nodojn en la rubujo."""
    node_svc = get_node_service()
    items = node_svc.get_trash(limit=limit)

    if not items:
        info(tr_multi(
            "Rubujo estas malplena.",
            "Trash is empty.",
            "La corbeille est vide.",
        ))
        return

    table = build_trash_table(
        items, "node_id",
        tr_multi("ID", "ID", "ID"),
        tr_multi("Etikedo", "Label", "Étiquette"),
        tr_multi("Forigita", "Deleted", "Supprimé"),
        get_label_from_etikedoj,
    )
    info(table)


# ── restaurigi (primary) ────────────────────────────────────────────


def _do_batch_restore(node_ids: list[str], yes: bool) -> None:
    """Execute batch restore using shared helpers."""
    batch_restore(
        node_ids,
        get_node_service,
        get_db(),
        "nodes_rubujo",
        "node_id",
        label_getter=get_label_from_etikedoj,
        yes=yes,
    )


@rubujo_app.command("restaurigi")
def restaurigi(
    node_ids: list[str] = typer.Argument(
        ...,
        help=tr_multi(
            "Nod-indeksoj (pluraj)",
            "Node IDs (multiple)",
            "ID des nœuds (plusieurs)",
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
    """Restarigi nodojn el la rubujo.

    Examples:
        rubujo restaurigi hundo
        rubujo restaurigi hundo mamulo
    """
    _do_batch_restore(node_ids, yes)


@rubujo_app.command("restaŭrigi", hidden=True, deprecated=True)
def restaurigi_deprecated_accent(
    node_ids: list[str] = typer.Argument(
        ...,
        help=tr_multi(
            "Nod-indeksoj (pluraj)",
            "Node IDs (multiple)",
            "ID des nœuds (plusieurs)",
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
    """Deprecated: uzu 'restaurigi' anstataŭe."""
    warning(tr_multi(
        "'restaŭrigi' estas malrekomendita, uzu 'restaurigi'",
        "'restaŭrigi' is deprecated, use 'restaurigi'",
        "'restaŭrigi' est déprécié, utilisez 'restaurigi'",
    ))
    _do_batch_restore(node_ids, yes)


@rubujo_app.command("restauxrigi", hidden=True, deprecated=True)
def restaurigi_deprecated_x(
    node_ids: list[str] = typer.Argument(
        ...,
        help=tr_multi(
            "Nod-indeksoj (pluraj)",
            "Node IDs (multiple)",
            "ID des nœuds (plusieurs)",
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
    """Deprecated: uzu 'restaurigi' anstataŭe."""
    warning(tr_multi(
        "'restauxrigi' estas malrekomendita, uzu 'restaurigi'",
        "'restauxrigi' is deprecated, use 'restaurigi'",
        "'restauxrigi' est déprécié, utilisez 'restaurigi'",
    ))
    _do_batch_restore(node_ids, yes)


# ── malplenigi ────────────────────────────────────────────────────────


@rubujo_app.command("malplenigi")
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
    """Malplenigi la rubujon — permanente forigi ĉiujn forigitajn nodojn.

    Warning: This operation is irreversible. Deleted nodes cannot be recovered.
    """
    node_svc = get_node_service()

    # Gather items to be deleted (SQL-side filtering for --days)
    if days is not None:
        items = node_svc.get_trash_older_than(days)
        if not items:
            info(tr_multi(
                "Neniuj nodoj pli aĝaj ol {d} tagoj.",
                "No nodes older than {d} days.",
                "Aucun nœud plus vieux que {d} jours.",
            ).format(d=days))
            return
    else:
        items = node_svc.get_trash(limit=99999)
        if not items:
            info(tr_multi(
                "Rubujo estas jam malplena.",
                "Trash is already empty.",
                "La corbeille est déjà vide.",
            ))
            return

    if not yes:
        warning(tr_multi(
            "AVERTO: tiu ago estas necivilebla!",
            "WARNING: this action is irreversible!",
            "AVERTISSEMENT : cette action est irréversible !",
        ))

        table = build_trash_table(
            items, "node_id",
            tr_multi("ID", "ID", "ID"),
            tr_multi("Etikedo", "Label", "Étiquette"),
            tr_multi("Forigita", "Deleted", "Supprimé"),
            get_label_from_etikedoj,
        )
        info(table)

        if not confirm_action(
            tr_multi(
                "Ĉu permanente forigi {n} nodojn el la rubujo?",
                "Permanently delete {n} nodes from trash?",
                "Supprimer définitivement {n} nœuds de la corbeille?",
            ).format(n=len(items)),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    if days is not None:
        deleted_count = node_svc.empty_trash(days=days)
    else:
        deleted_count = node_svc.empty_all_trash()

    info(tr_multi(
        "Rubujo malplenigita: {n} nodoj forigitaj.",
        "Trash emptied: {n} nodes deleted.",
        "Corbeille vidée : {n} nœuds supprimés.",
    ).format(n=deleted_count))


# ── forigi (permanent delete from trash) ─────────────────────────────


@rubujo_app.command("forigi")
def forigi(
    node_ids: list[str] = typer.Argument(
        ...,
        help=tr_multi(
            "Nod-indeksoj por permanenta forigo (pluraj)",
            "Node IDs for permanent deletion (multiple)",
            "ID des nœuds pour suppression définitive (plusieurs)",
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
    """Permanente forigi nodojn el rubujo.

    Examples:
        rubujo forigi hundo
        rubujo forigi hundo mamulo
    """
    batch_permanent_delete(
        node_ids,
        get_node_service,
        get_db(),
        "nodes_rubujo",
        "node_id",
        label_getter=get_label_from_etikedoj,
        yes=yes,
    )
