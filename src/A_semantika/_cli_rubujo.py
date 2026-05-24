"""Rubujo (trash) subcommand group: ls, restaŭrigi, malplenigi, forigi.

Provides CLI for managing soft-deleted nodes.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika.data.storage import label_from_json
from A_semantika.service import get_node_service, get_triple_service

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
        table.add_row(n.get("node_id", "?")[:8], label, deleted_at)

    info(table)


@rubujo_app.command("restauxrigi")
def restauxrigi(
    node_id: str = typer.Argument(
        ...,
        help=tr_multi(
            "Nod-indekso aŭ prefikso",
            "Node ID or prefix",
            "ID ou préfixe du nœud",
        ),
    ),
) -> None:
    """Restarigi nodon el la rubujo (restore).

    Accepts ``restauxrigi`` (x-convention) as well as ``restaŭrigi``
    for keyboard portability.
    """
    _do_restore(node_id)


@rubujo_app.command("restaŭrigi")
def restaurigi(
    node_id: str = typer.Argument(
        ...,
        help=tr_multi(
            "Nod-indekso aŭ prefikso",
            "Node ID or prefix",
            "ID ou préfixe du nœud",
        ),
    ),
) -> None:
    """Restarigi nodon el la rubujo.

    Esperanto-ortografia varianto (bezonas ŝ-topan klavaron).
    """
    _do_restore(node_id)


def _resolve_trash_node(node_svc, node_id: str) -> dict | None:
    """Resolve a node_id prefix against the trash table (nodes_rubujo)."""
    triple_svc = get_triple_service()

    # Full match first
    entry = triple_svc.db.execute_one(
        "SELECT * FROM nodes_rubujo WHERE node_id = ?", (node_id,)
    )
    if entry:
        return entry

    # Prefix match (LIKE)
    entries = triple_svc.db.execute(
        "SELECT * FROM nodes_rubujo WHERE node_id LIKE ?", (f"{node_id}%",)
    )
    if not entries:
        return None
    if len(entries) > 1:
        msg = f"Node ID prefix '{node_id}' is ambiguous ({len(entries)} matches)"
        raise AmbiguousUUIDError(msg)
    return entries[0]


def _do_restore(node_id: str) -> None:
    """Shared logic for restaŭrigi / restauxrigi."""
    node_svc = get_node_service()
    try:
        node = _resolve_trash_node(node_svc, node_id)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua prefikso: {e}",
            "Ambiguous prefix: {e}",
            "Préfixe ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e

    if not node:
        error(tr_multi(
            "Nodo ne trovita en rubujo: {u}",
            "Node not found in trash: {u}",
            "Nœud non trouvé dans la corbeille : {u}",
        ).format(u=node_id))
        raise typer.Exit(1)

    restored = node_svc.restore(node["node_id"])
    if not restored:
        error(tr_multi(
            "Ne povis restarigi nodon: {u}",
            "Could not restore node: {u}",
            "Impossible de restaurer le nœud : {u}",
        ).format(u=node_id))
        raise typer.Exit(1)

    info(tr_multi(
        "Nodo restarigita: {u}",
        "Node restored: {u}",
        "Nœud restauré : {u}",
    ).format(u=node["node_id"][:8]))


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
    """Malplenigi la rubujon."""
    node_svc = get_node_service()

    # Count items to be deleted
    items = node_svc.get_trash(limit=99999)
    if not items:
        info(tr_multi(
            "Rubujo estas jam malplena.",
            "Trash is already empty.",
            "La corbeille est déjà vide.",
        ))
        return

    # If days filter, count matching items
    if days is not None:
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        items = [i for i in items if i.get("forigita_je", "") < cutoff.isoformat()]
        if not items:
            info(tr_multi(
                "Neniuj nodoj pli aĝaj ol {d} tagoj.",
                "No nodes older than {d} days.",
                "Aucun nœud plus vieux que {d} jours.",
            ).format(d=days))
            return

    if not yes:
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
        node_svc.empty_trash(days=days)
    else:
        node_svc.empty_trash()

    info(tr_multi(
        "Rubujo malplenigita: {n} nodoj forigitaj.",
        "Trash emptied: {n} nodes deleted.",
        "Corbeille vidée : {n} nœuds supprimés.",
    ).format(n=len(items)))


@rubujo_app.command("forigi")
def forigi(
    node_id: str = typer.Argument(
        ...,
        help=tr_multi(
            "Nod-indekso aŭ prefikso por permanenta forigo",
            "Node ID or prefix for permanent deletion",
            "ID ou préfixe du nœud pour suppression définitive",
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
    """Permanente forigi nodon el rubujo."""
    node_svc = get_node_service()
    try:
        node = _resolve_trash_node(node_svc, node_id)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua prefikso: {e}",
            "Ambiguous prefix: {e}",
            "Préfixe ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e

    if not node:
        error(tr_multi(
            "Nodo ne trovita en rubujo: {u}",
            "Node not found in trash: {u}",
            "Nœud non trouvé dans la corbeille : {u}",
        ).format(u=node_id))
        raise typer.Exit(1)

    if not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu permanente forigi nodon {u}?",
                "Permanently delete node {u}?",
                "Supprimer définitivement le nœud {u}?",
            ).format(u=node["node_id"][:8]),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    node_svc.permanent_delete(node["node_id"])
    info(tr_multi(
        "Nodo permanente forigita: {u}",
        "Node permanently deleted: {u}",
        "Nœud définitivement supprimé : {u}",
    ).format(u=node["node_id"][:8]))
