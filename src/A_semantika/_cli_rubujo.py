"""Rubujo (trash) subcommand group: ls, restaurigi, malplenigi, forigi.

Provides CLI for managing soft-deleted nodes.
restaurigi accepts multiple positional args. The old accented aliases
restaŭrigi and restauxrigi are kept as hidden deprecated aliases.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika.data.storage import get_db, label_from_json
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

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("ID", no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)
    table.add_column(tr_multi("Forigita", "Deleted", "Supprimé"), no_wrap=True)

    for n in items:
        label = label_from_json(n.get("etikedoj", "{}"))
        deleted_at = n.get("forigita_je", "")[:19]  # Truncate ISO to seconds
        nid = n.get("node_id", "?")
        display_id = nid[:16] if len(nid) > 16 else nid
        table.add_row(display_id, label, deleted_at)

    info(table)


# ── Shared helpers ──────────────────────────────────────────────────


def _resolve_trash_node(node_id: str) -> dict | None:
    """Resolve a node_id prefix against the trash table (nodes_rubujo)."""
    db = get_db()

    # Full match first (case-insensitive)
    entry = db.execute_one(
        "SELECT * FROM nodes_rubujo WHERE node_id = ? COLLATE NOCASE", (node_id,)
    )
    if entry:
        return entry

    # Prefix match (LIKE + COLLATE NOCASE for case-insensitive search)
    entries = db.execute(
        "SELECT * FROM nodes_rubujo WHERE node_id LIKE ? COLLATE NOCASE", (f"{node_id}%",)
    )
    if not entries:
        return None
    if len(entries) > 1:
        msg = f"Node ID prefix '{node_id}' is ambiguous ({len(entries)} matches)"
        raise AmbiguousUUIDError(msg)
    return entries[0]


def _batch_resolve_trash_nodes(
    node_ids: list[str],
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Resolve multiple node_id prefixes against the trash table.

    Returns (resolved_nodes, errors) where errors is a list of
    (input, reason) tuples for unresolvable IDs.
    """
    resolved: list[dict] = []
    errors: list[tuple[str, str]] = []

    for nid in node_ids:
        try:
            node = _resolve_trash_node(nid)
            if node:
                resolved.append(node)
            else:
                errors.append((nid, tr_multi(
                    "ne trovita en rubujo",
                    "not found in trash",
                    "non trouvé dans la corbeille",
                )))
        except AmbiguousUUIDError:
            errors.append((nid, tr_multi(
                "ambigua prefikso",
                "ambiguous prefix",
                "préfixe ambigu",
            )))

    return resolved, errors


# ── restaurigi (primary) ────────────────────────────────────────────


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
    _batch_restore(node_ids, yes)


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
    _batch_restore(node_ids, yes)


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
    _batch_restore(node_ids, yes)


def _batch_restore(node_ids: list[str], yes: bool) -> None:
    """Shared batch-restore logic."""
    node_svc = get_node_service()

    resolved, errors = _batch_resolve_trash_nodes(node_ids)

    # Report resolution errors
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

    # Single item: skip confirmation (user already specified exact item)
    if not yes and len(resolved) >= 2:
        from A.utils.interactive import confirm_action

        label_list = ", ".join(
            label_from_json(n.get("etikedoj", "{}")) or (
                n["node_id"][:16] if len(n["node_id"]) > 16 else n["node_id"]
            )
            for n in resolved
        )
        if not confirm_action(
            tr_multi(
                "Ĉu restarigi {n} nodojn: {labels}?",
                "Restore {n} nodes: {labels}?",
                "Restaurer {n} nœuds : {labels}?",
            ).format(n=len(resolved), labels=label_list),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    restored = 0
    for node in resolved:
        try:
            result = node_svc.restore(node["node_id"])
            if result:
                restored += 1
                info(tr_multi(
                    "Restarigita: {u}",
                    "Restored: {u}",
                    "Restauré : {u}",
                ).format(u=node["node_id"][:16]))
        except (sqlite3.Error, ValueError) as e:
            error(tr_multi(
                "Eraro restarigante {u}: {e}",
                "Error restoring {u}: {e}",
                "Erreur lors de la restauration de {u} : {e}",
            ).format(u=node["node_id"][:16], e=str(e)))

    info(tr_multi(
        "Restarigis {r} el {t} nodoj.",
        "Restored {r} of {t} nodes.",
        "Restauré {r} sur {t} nœuds.",
    ).format(r=restored, t=len(resolved)))


# ── malplenigi ──────────────────────────────────────────────────────


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
        # Show warning and list of items
        warning(tr_multi(
            "AVERTO: tiu ago estas necivilebla!",
            "WARNING: this action is irreversible!",
            "AVERTISSEMENT : cette action est irréversible !",
        ))

        table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
        table.add_column("ID", no_wrap=True)
        table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)
        table.add_column(tr_multi("Forigita", "Deleted", "Supprimé"), no_wrap=True)

        for n in items:
            label = label_from_json(n.get("etikedoj", "{}"))
            deleted_at = n.get("forigita_je", "")[:19]
            nid = n.get("node_id", "?")
            display_id = nid[:16] if len(nid) > 16 else nid
            table.add_row(display_id, label, deleted_at)

        info(table)

        from A.utils.interactive import confirm_action

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


# ── forigi (permanent delete from trash) ────────────────────────────


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
    node_svc = get_node_service()

    resolved, errors = _batch_resolve_trash_nodes(node_ids)

    # Report resolution errors
    for input_val, reason in errors:
        error(tr_multi(
            "Forigi {i}: {r}",
            "Delete {i}: {r}",
            "Supprimer {i} : {r}",
        ).format(i=input_val, r=reason))

    if not resolved:
        error(tr_multi(
            "Nenio forigebla el rubujo.",
            "Nothing to delete from trash.",
            "Rien à supprimer de la corbeille.",
        ))
        raise typer.Exit(1)

    # Single item: skip confirmation (user already specified exact item)
    if not yes and len(resolved) >= 2:
        # Show list of items to be permanently deleted
        table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
        table.add_column("ID", no_wrap=True)
        table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)
        table.add_column(tr_multi("Forigita", "Deleted", "Supprimé"), no_wrap=True)

        for n in resolved:
            label = label_from_json(n.get("etikedoj", "{}"))
            deleted_at = n.get("forigita_je", "")[:19]
            nid = n.get("node_id", "?")
            display_id = nid[:16] if len(nid) > 16 else nid
            table.add_row(display_id, label, deleted_at)

        info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu permanente forigi {n} nodojn el la rubujo?",
                "Permanently delete {n} nodes from trash?",
                "Supprimer définitivement {n} nœuds de la corbeille?",
            ).format(n=len(resolved)),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    deleted = 0
    for node in resolved:
        try:
            node_svc.permanent_delete(node["node_id"])
            deleted += 1
            info(tr_multi(
                "Permanente forigita: {u}",
                "Permanently deleted: {u}",
                "Définitivement supprimé : {u}",
            ).format(u=node["node_id"][:16]))
        except (sqlite3.Error, ValueError) as e:
            error(tr_multi(
                "Eraro forigante {u}: {e}",
                "Error deleting {u}: {e}",
                "Erreur lors de la suppression de {u} : {e}",
            ).format(u=node["node_id"][:16], e=str(e)))

    info(tr_multi(
        "Permanente forigis {d} el {t} nodoj.",
        "Permanently deleted {d} of {t} nodes.",
        "Définitivement supprimé {d} sur {t} nœuds.",
    ).format(d=deleted, t=len(resolved)))
