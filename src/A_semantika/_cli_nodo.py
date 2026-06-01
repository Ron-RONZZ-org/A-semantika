"""Nodo subcommand group CLI: ls, vidi, aldoni, modifi, forigi, serci.
"""
from __future__ import annotations

import json
from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika._cli_nodo_crud import aldoni, modifi
from A_semantika._cli_nodo_forigi import forigi
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika.data.storage import label_from_json
from A_semantika.service import get_node_service


nodo_app = typer.Typer(
    name="nodo",
    help=tr_multi(
        "Administri nodojn (entojn en la grafeo)",
        "Manage nodes (entities in the graph)",
        "Gérer les nœuds (entités du graphe)",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

# Register imported CRUD commands
nodo_app.command(name="aldoni")(aldoni)
nodo_app.command(name="modifi")(modifi)
nodo_app.command(name="forigi")(forigi)


@nodo_app.command("ls")
def ls(
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
    lingvo: Optional[str] = typer.Option(None, "--lingvo", help=tr_multi(
        "Lingva kodo por etikedoj (ekz. eo, en, fr)",
        "Language code for labels (e.g. eo, en, fr)",
        "Code de langue pour les étiquettes (ex. eo, en, fr)",
    )),
) -> None:
    """Listi ĉiujn nodojn."""
    node_svc = get_node_service()
    nodes = node_svc.list(limit=limit)
    if not nodes:
        info(tr_multi("Neniuj nodoj.", "No nodes.", "Aucun nœud."))
        return

    lang_fallback = (lingvo, "eo", "en") if lingvo else ("eo", "en")

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("ID", no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)

    # Detect ambiguous 16-char prefixes and show full UUIDs if needed
    prefixes: set[str] = set()
    ambiguous: set[str] = set()
    for n in nodes:
        pref = n["node_id"][:16]
        if pref in prefixes:
            ambiguous.add(pref)
        prefixes.add(pref)

    for n in nodes:
        label = label_from_json(n["etikedoj"], lang_fallback)
        disp = n["node_id"] if n["node_id"][:16] in ambiguous else n["node_id"][:16]
        table.add_row(disp, label)

    info(table)


@nodo_app.command("vidi")
def vidi(
    node_id: str = typer.Argument(..., help=tr_multi("Nod-indekso", "Node ID", "ID du nœud")),
) -> None:
    """Vidi detalojn de nodo."""
    node_svc = get_node_service()
    try:
        node = node_svc.resolve_node_id_prefix(node_id)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua prefikso: {e}", "Ambiguous prefix: {e}", "Préfixe ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not node:
        # Fallback: substring match
        try:
            node = node_svc.resolve_node_id_substring(node_id)
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua nodo: {e}", "Ambiguous node: {e}", "Nœud ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1) from e
    if not node:
        error(tr_multi("Nodo ne trovita: {u}", "Node not found: {u}", "Nœud non trouvé : {u}").format(u=node_id))
        raise typer.Exit(1)

    try:
        labels = json.loads(node["etikedoj"])
        defns = json.loads(node["difinoj"])
    except (json.JSONDecodeError, TypeError):
        labels = {}
        defns = {}

    if not isinstance(labels, dict):
        labels = {}
    if not isinstance(defns, dict):
        defns = {}

    info(tr_multi("ID: {u}", "ID: {u}", "ID : {u}").format(u=node["node_id"]))
    for lang, val in labels.items():
        info(f"  {lang}: {val}")
    if defns:
        info(tr_multi("Difinoj:", "Definitions:", "Définitions :"))
        for lang, val in defns.items():
            info(f"  {lang}: {val}")
    info(tr_multi("Kreita: {d}", "Created: {d}", "Créé : {d}").format(d=node["kreita_je"]))
    info(tr_multi("Modifita: {d}", "Modified: {d}", "Modifié : {d}").format(d=node["modifita_je"]))


@nodo_app.command("serci")
def serci(
    query: str = typer.Argument(..., help=tr_multi("Serĉa teksto", "Search text", "Texte de recherche")),
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
    lingvo: Optional[str] = typer.Option(None, "--lingvo", help=tr_multi(
        "Lingva kodo por etikedoj (ekz. eo, en, fr)",
        "Language code for labels (e.g. eo, en, fr)",
        "Code de langue pour les étiquettes (ex. eo, en, fr)",
    )),
) -> None:
    """Serĉi nodojn per teksto aŭ ID (FTS5 + ID LIKE)."""
    node_svc = get_node_service()

    # Search by label/definition (FTS5) AND by node_id (LIKE)
    label_results = node_svc.search(query, limit=limit)

    # Also search by node_id (LIKE with wildcard escaping, substring match;
    # resolve_node_id_prefix in _node_search.py does exact → prefix → substring)
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    id_results = node_svc.db.execute(
        "SELECT * FROM nodes WHERE node_id LIKE ? COLLATE NOCASE ESCAPE '\\' LIMIT ?",
        (f"%{escaped}%", limit),
    )

    # Merge and deduplicate (label_results first, then append new IDs)
    seen: set[str] = set()
    results: list[dict] = []
    for n in label_results:
        nid = n["node_id"]
        if nid not in seen:
            seen.add(nid)
            results.append(n)
    for n in id_results:
        nid = n["node_id"]
        if nid not in seen:
            seen.add(nid)
            results.append(n)

    if not results:
        info(tr_multi("Neniuj nodoj trovitaj.", "No nodes found.", "Aucun nœud trouvé."))
        return

    lang_fallback = (lingvo, "eo", "en") if lingvo else ("eo", "en")

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("ID", no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)

    for n in results:
        label = label_from_json(n["etikedoj"], lang_fallback)
        table.add_row(n["node_id"][:16], label)

    info(table)
