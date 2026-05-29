"""Nodo forigi subcommand — extracted to keep _cli_nodo_crud.py < 500 lines."""
from __future__ import annotations

import sqlite3

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika.service import get_node_service, get_predicate_service, get_triple_service


def _format_delete_error(nid: str, error: Exception) -> str:
    """Format a human-readable delete error from an IntegrityError or DatabaseError.

    Args:
        nid: Node ID (for reference in the message).
        error: The caught exception.

    Returns:
        A user-facing error message string (already localized via tr_multi).
    """
    err_msg = str(error)
    if isinstance(error, sqlite3.IntegrityError):
        if "UNIQUE constraint failed" in err_msg:
            return tr_multi(
                "Nodo {u} jam estas en la rubujo.",
                "Node {u} is already in the trash.",
                "Le nœud {u} est déjà dans la corbeille.",
            ).format(u=nid)
        if "FOREIGN KEY constraint failed" in err_msg:
            return tr_multi(
                "Nodo {u} havas arkojn. Forigu ilin unue aŭ uzu la flagon --jes.",
                "Node {u} has arcs. Delete them first or use the --jes flag.",
                "Le nœud {u} a des arcs. Supprimez-les d'abord ou utilisez le drapeau --jes.",
            )
        return err_msg
    # Log the actual exception detail before returning user-facing message
    warning(f"Delete error for {nid}: {type(error).__name__}: {err_msg}")
    return tr_multi(
        "Eraro forigante {u}: {e}",
        "Error deleting {u}: {e}",
        "Erreur lors de la suppression de {u} : {e}",
    ).format(u=nid, e=err_msg)


def forigi(
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
    """Forigi nodojn."""
    node_svc = get_node_service()
    triple_svc = get_triple_service()

    # Phase 1: Resolve all identifiers
    resolved: list[dict] = []
    errors: list[tuple[str, str]] = []

    for nid in node_ids:
        try:
            node = node_svc.resolve_node_id_prefix(nid)
            if node:
                resolved.append(node)
            else:
                errors.append((nid, tr_multi("ne trovita", "not found", "non trouvé")))
        except AmbiguousUUIDError as e:
            errors.append((nid, tr_multi(
                "ambigua prefikso: {e}",
                "ambiguous prefix: {e}",
                "préfixe ambigu : {e}",
            ).format(e=str(e))))

    # Report resolution errors
    for input_val, reason in errors:
        error(tr_multi(
            "Forigi {i}: {r}", "Delete {i}: {r}", "Supprimer {i} : {r}",
        ).format(i=input_val, r=reason))

    if not resolved:
        error(tr_multi("Nenio forigebla.", "Nothing to delete.", "Rien à supprimer."))
        raise typer.Exit(1)

    # Collect triples referencing any of the resolved nodes (single bulk query)
    pred_svc = get_predicate_service()
    resolved_ids_list = [n["node_id"] for n in resolved]
    all_triples = triple_svc.get_by_nodes(resolved_ids_list)

    # Build set of resolved node_ids that have triples
    nodes_with_triples: set[str] = set()
    for t in all_triples:
        nodes_with_triples.add(t["subject_uuid"])
        if t["object_type"] == "uri":
            nodes_with_triples.add(t["object_value"])
    resolved_ids = {n["node_id"] for n in resolved}
    nodes_with_triples &= resolved_ids

    # Phase 2: Preview and confirmation
    requires_confirm = len(resolved) >= 2 or all_triples
    if not yes and requires_confirm:
        # Nodes preview table
        table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
        table.add_column("ID", no_wrap=True)
        table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)

        for node in resolved:
            label = resolve_node_label(node_svc, node["node_id"])
            table.add_row(node["node_id"][:16], label)
        info(table)

        # Triples to be deleted
        if all_triples:
            ttable = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
            ttable.add_column(tr_multi("Subjekto", "Subject", "Sujet"))
            ttable.add_column(tr_multi("Predikato", "Predicate", "Prédicat"))
            ttable.add_column(tr_multi("Objekto", "Object", "Objet"))
            for t in all_triples:
                subj_label = resolve_node_label(node_svc, t["subject_uuid"])
                pred_label = resolve_predicate_label(pred_svc, t["predicate_id"])
                if t["object_type"] == "uri":
                    obj_label = resolve_node_label(node_svc, t["object_value"])
                else:
                    obj_label = t["object_value"]
                    if t.get("object_lang"):
                        obj_label += f"@{t['object_lang']}"
                ttable.add_row(subj_label, pred_label, obj_label)
            info(tr_multi(
                "Arkoj forigotaj:",
                "Triples to be deleted:",
                "Triplets à supprimer :",
            ))
            info(ttable)

        # Build confirmation message with triple warning
        confirm_msg = tr_multi(
            "Ĉu forigi {n} nodojn?", "Delete {n} nodes?", "Supprimer {n} nœuds?",
        ).format(n=len(resolved))
        if all_triples:
            confirm_msg = (
                tr_multi(
                    "Atenton: {t} arkoj estos forigitaj kune kun la nodoj. ",
                    "Warning: {t} arcs will be deleted together with the nodes. ",
                    "Attention : {t} arcs seront supprimés avec les nœuds. ",
                ).format(t=len(all_triples))
                + confirm_msg
            )

        from A.utils.interactive import confirm_action

        if not confirm_action(confirm_msg, default=False):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Phase 3: Delete triples then nodes
    deleted = 0
    for node in resolved:
        nid = node["node_id"]
        try:
            # Cascade: delete referencing triples first (FK constraint)
            if nid in nodes_with_triples:
                triple_svc.remove_by_node(nid)
            node_svc.delete(nid)
            deleted += 1
        except (sqlite3.IntegrityError, sqlite3.DatabaseError) as e:
            error(_format_delete_error(nid, e))

    info(tr_multi(
        "Forigis {d} el {t} nodoj.",
        "Deleted {d} of {t} nodes.",
        "Supprimé {d} sur {t} nœuds.",
    ).format(d=deleted, t=len(resolved)))
