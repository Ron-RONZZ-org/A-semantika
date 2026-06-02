"""Nodo kunfandi (merge) subcommand — merge two nodes into one.

Syntax::

    A semantika nodo kunfandi <fonto> <celo> [--jes]

The *fonto* (source) node is merged INTO the *celo* (target) node.
The source node is deleted after all triples and labels have been
reassigned to the target.
"""
from __future__ import annotations

import json

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._node_helpers import AmbiguousUUIDError, truncate_uuid
from A_semantika._node_service import NodeService
from A_semantika._preview import resolve_node_label
from A_semantika._triple_service import TripleService
from A_semantika.data.storage import label_from_json
from A_semantika.service import get_node_service, get_triple_service


def _build_merge_preview(
    node_svc: NodeService,
    triple_svc: TripleService,
    source_id: str,
    target_id: str,
) -> Table | None:
    """Build a preview table showing what will happen during merge.

    Returns ``None`` if either node is not found.
    """
    source = node_svc.get(source_id)
    target = node_svc.get(target_id)
    if not source or not target:
        return None

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Kampo", "Field", "Champ"), no_wrap=True)
    table.add_column(
        tr_multi("Fonto ({id})", "Source ({id})", "Source ({id})").format(id=truncate_uuid(source_id)),
        no_wrap=True,
    )
    table.add_column(
        tr_multi("Celo ({id}) → Rezulto", "Target ({id}) → Result", "Cible ({id}) → Résultat").format(id=truncate_uuid(target_id)),
        no_wrap=True,
    )

    # Source label
    src_label = label_from_json(source["etikedoj"], ("eo", "en"))
    tgt_label = label_from_json(target["etikedoj"], ("eo", "en"))
    table.add_row(
        tr_multi("Etikedo", "Label", "Étiquette"),
        src_label or "—",
        tgt_label or "—",
    )

    # Labels detail (languages)
    try:
        src_lbl_dict = json.loads(source["etikedoj"]) if isinstance(source["etikedoj"], str) else source["etikedoj"]
    except (json.JSONDecodeError, TypeError):
        src_lbl_dict = {}
    try:
        tgt_lbl_dict = json.loads(target["etikedoj"]) if isinstance(target["etikedoj"], str) else target["etikedoj"]
    except (json.JSONDecodeError, TypeError):
        tgt_lbl_dict = {}

    if not isinstance(src_lbl_dict, dict):
        src_lbl_dict = {}
    if not isinstance(tgt_lbl_dict, dict):
        tgt_lbl_dict = {}

    # Show language-level detail only if there are languages
    if isinstance(src_lbl_dict, dict) and isinstance(tgt_lbl_dict, dict):
        merged_lbls = {**src_lbl_dict, **tgt_lbl_dict}
        src_lines = "\n".join(f"{k}: {v}" for k, v in sorted(src_lbl_dict.items())) if src_lbl_dict else "—"
        merged_lines = "\n".join(f"{k}: {v}" for k, v in sorted(merged_lbls.items())) if merged_lbls else "—"
        table.add_row(
            tr_multi("Etikedoj (senv.), difinoj", "Labels (langs) / definitions", "Étiquettes (langues) / définitions"),
            src_lines,
            merged_lines,
        )

    # Triple count
    src_triple_count = triple_svc.count_by_subject_or_object(source_id)
    tgt_triple_count = triple_svc.count_by_subject_or_object(target_id)

    # Count how many triples will actually be reassigned (not skipped)
    # We do a rough estimate: all source triples, minus those that collide
    collisions_subj = 0
    collisions_obj = 0
    if src_triple_count > 0:
        src_triples = triple_svc.get_by_node(source_id)
        for t in src_triples:
            if t["subject_uuid"] == source_id:
                dup = triple_svc.db.execute_one(
                    "SELECT 1 FROM triples WHERE subject_uuid = ? AND predicate_id = ? "
                    "AND object_value = ? AND object_type = ?",
                    (target_id, t["predicate_id"], t["object_value"], t["object_type"]),
                )
                if dup:
                    collisions_subj += 1
            if t["object_type"] == "uri" and t["object_value"] == source_id:
                dup = triple_svc.db.execute_one(
                    "SELECT 1 FROM triples WHERE subject_uuid = ? AND predicate_id = ? "
                    "AND object_value = ? AND object_type = ?",
                    (t["subject_uuid"], t["predicate_id"], target_id, t["object_type"]),
                )
                if dup:
                    collisions_obj += 1

    reassigned = src_triple_count - collisions_subj - collisions_obj
    table.add_row(
        tr_multi("Arkoj", "Triples", "Triplets"),
        tr_multi("{n} arkoj", "{n} triples", "{n} triplets").format(n=src_triple_count),
        tr_multi("{n} reasignotaj ({c} preterlasitaj)", "{n} to reassign ({c} skipped)", "{n} à réaffecter ({c} ignorés)").format(
            n=reassigned, c=collisions_subj + collisions_obj,
        ),
    )

    return table


def kunfandi(
    fonto: str = typer.Argument(..., help=tr_multi(
        "Fonto-nodo (forigota post kunfando)",
        "Source node (will be deleted after merge)",
        "Nœud source (sera supprimé après la fusion)",
    )),
    celo: str = typer.Argument(..., help=tr_multi(
        "Celo-nodo (posta ricevonta ĉiujn datumojn)",
        "Target node (will receive all data)",
        "Nœud cible (recevra toutes les données)",
    )),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi(
        "Preterpasi konfirmon",
        "Skip confirmation",
        "Ignorer la confirmation",
    )),
) -> None:
    """Kunfandi du nodojn en unu.

    All triples, labels, and definitions from the *fonto* (source) node
    are merged into the *celo* (target) node.  The source node is then
    deleted.

    On label/definition conflicts the target's values take precedence.
    On triple conflicts (duplicate subject-predicate-object) the target's
    triples are kept and the source's are silently dropped.
    """
    node_svc = get_node_service()
    triple_svc = get_triple_service()

    # Resolve source node
    try:
        src_node = node_svc.resolve_node_id_prefix(fonto)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua fonto-prefikso: {e}",
            "Ambiguous source prefix: {e}",
            "Préfixe source ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not src_node:
        try:
            src_node = node_svc.resolve_node_id_substring(fonto)
        except AmbiguousUUIDError as e:
            error(tr_multi(
                "Ambigua fonto-prefikso: {e}",
                "Ambiguous source prefix: {e}",
                "Préfixe source ambigu : {e}",
            ).format(e=str(e)))
            raise typer.Exit(1) from e
    if not src_node:
        error(tr_multi(
            "Fonto-nodo ne trovita: {u}",
            "Source node not found: {u}",
            "Nœud source non trouvé : {u}",
        ).format(u=fonto))
        raise typer.Exit(1)
    source_id = src_node["node_id"]

    # Resolve target node
    try:
        tgt_node = node_svc.resolve_node_id_prefix(celo)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua celo-prefikso: {e}",
            "Ambiguous target prefix: {e}",
            "Préfixe cible ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not tgt_node:
        try:
            tgt_node = node_svc.resolve_node_id_substring(celo)
        except AmbiguousUUIDError as e:
            error(tr_multi(
                "Ambigua celo-prefikso: {e}",
                "Ambiguous target prefix: {e}",
                "Préfixe cible ambigu : {e}",
            ).format(e=str(e)))
            raise typer.Exit(1) from e
    if not tgt_node:
        error(tr_multi(
            "Celo-nodo ne trovita: {u}",
            "Target node not found: {u}",
            "Nœud cible non trouvé : {u}",
        ).format(u=celo))
        raise typer.Exit(1)
    target_id = tgt_node["node_id"]

    # Same-node guard
    if source_id == target_id:
        error(tr_multi(
            "Fonto kaj celo estas la sama nodo: {u}",
            "Source and target are the same node: {u}",
            "La source et la cible sont le même nœud : {u}",
        ).format(u=source_id))
        raise typer.Exit(1)

    # Show preview
    screen = _build_merge_preview(node_svc, triple_svc, source_id, target_id)
    if not screen:
        error(tr_multi(
            "Eraro konstruanta antaŭrigardon.",
            "Error building preview.",
            "Erreur lors de la construction de l'aperçu.",
        ))
        raise typer.Exit(1)

    info("")
    info(screen)

    # Confirm
    if not yes:
        src_label = resolve_node_label(node_svc, source_id)
        tgt_label = resolve_node_label(node_svc, target_id)
        msg = tr_multi(
            "Ĉu kunfandi nodon {s} EN {t}?",
            "Merge node {s} INTO {t}?",
            "Fusionner le nœud {s} DANS {t}?",
        ).format(s=src_label, t=tgt_label)
        if not confirm_action(msg, default=False):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Execute merge
    try:
        node_svc.merge_nodes(source_id, target_id)
    except ValueError as e:
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e

    tgt_label = resolve_node_label(node_svc, target_id)
    info(tr_multi(
        "Nodoj kunfanditaj: {s} → {t} ({label})",
        "Nodes merged: {s} → {t} ({label})",
        "Nœuds fusionnés : {s} → {t} ({label})",
    ).format(
        s=source_id,
        t=target_id,
        label=tgt_label,
    ))
