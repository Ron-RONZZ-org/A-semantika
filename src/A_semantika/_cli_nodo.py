"""Nodo subcommand group CLI: ls, vidi, aldoni, modifi, forigi, serci.
"""
from __future__ import annotations

import json
from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import confirm_node_with_arcs, resolve_node_label
from A_semantika.service import get_node_service, get_predicate_service, get_triple_service

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


@nodo_app.command("ls")
def ls(
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
) -> None:
    """Listi ĉiujn nodojn."""
    node_svc = get_node_service()
    nodes = node_svc.list(limit=limit)
    if not nodes:
        info(tr_multi("Neniuj nodoj.", "No nodes.", "Aucun nœud."))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("UUID", no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)

    for n in nodes:
        try:
            labels = json.loads(n["etikedoj"])
            label = labels.get("eo") or labels.get("en") or ""
        except (json.JSONDecodeError, TypeError):
            label = ""
        table.add_row(n["uuid"][:8], label)

    info(table)


@nodo_app.command("vidi")
def vidi(
    uuid: str = typer.Argument(..., help=tr_multi("Nodo UUID-prefikso", "Node UUID prefix", "Préfixe UUID du nœud")),
) -> None:
    """Vidi detalojn de nodo."""
    node_svc = get_node_service()
    try:
        node = node_svc.resolve_uuid_prefix(uuid)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua prefikso: {e}", "Ambiguous prefix: {e}", "Préfixe ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1)
    if not node:
        error(tr_multi("Nodo ne trovita: {u}", "Node not found: {u}", "Nœud non trouvé : {u}").format(u=uuid))
        raise typer.Exit(1)

    try:
        labels = json.loads(node["etikedoj"])
        defns = json.loads(node["difinoj"])
    except (json.JSONDecodeError, TypeError):
        labels = {}
        defns = {}

    info(tr_multi("UUID: {u}", "UUID: {u}", "UUID : {u}").format(u=node["uuid"]))
    for lang, val in labels.items() if isinstance(labels, dict) else []:
        info(f"  {lang}: {val}")
    if defns:
        info(tr_multi("Difinoj:", "Definitions:", "Définitions :"))
        for lang, val in defns.items() if isinstance(defns, dict) else []:
            info(f"  {lang}: {val}")
    info(tr_multi("Kreita: {d}", "Created: {d}", "Créé : {d}").format(d=node["kreita_je"]))
    info(tr_multi("Modifita: {d}", "Modified: {d}", "Modifié : {d}").format(d=node["modifita_je"]))


@nodo_app.command("aldoni")
def aldoni(
    uuid: Optional[str] = typer.Argument(None, help=tr_multi("UUID (malplena = aŭtomata)", "UUID (empty = auto-generate)", "UUID (vide = auto-généré)")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANG::TEKSTO", "Label as LANG::TEXT", "Étiquette au format LANG::TEXTE")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino en formo LANG::TEKSTO", "Definition as LANG::TEXT", "Définition au format LANG::TEXTE")),
    tipo: Optional[list[str]] = typer.Option(None, "-t", "--tipo", help=tr_multi("Tipo (rdf:type) UUID-prefikso", "Type (rdf:type) UUID prefix", "Type (rdf:type) préfixe UUID")),
    superklaso: Optional[list[str]] = typer.Option(None, "-so", "--superklaso", help=tr_multi("Superklaso (rdfs:subClassOf) UUID-prefikso", "Superclass (rdfs:subClassOf) UUID prefix", "Superclasse (rdfs:subClassOf) préfixe UUID")),
    ne: Optional[list[str]] = typer.Option(None, "--ne", help=tr_multi("Malakorda (owl:disjointWith) UUID-prefikso", "Disjoint (owl:disjointWith) UUID prefix", "Disjoint (owl:disjointWith) préfixe UUID")),
    invers: Optional[list[str]] = typer.Option(None, "--invers", "-iv", help=tr_multi("Inversa (owl:inverseOf) UUID-prefikso", "Inverse (owl:inverseOf) UUID prefix", "Inverse (owl:inverseOf) préfixe UUID")),
    yes: bool = typer.Option(False, "-y", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Aldoni novan nodon kun laŭvolaj arkoj."""
    node_svc = get_node_service()

    # Parse labels and definitions
    labels_dict: dict[str, str] = {}
    defs_dict: dict[str, str] = {}
    if etikedoj:
        for e in etikedoj:
            if "::" in e:
                lang, _, text = e.partition("::")
                labels_dict[lang] = text
    if difinoj:
        for d in difinoj:
            if "::" in d:
                lang, _, text = d.partition("::")
                defs_dict[lang] = text

    data: dict = {
        "etikedoj": labels_dict,
        "difinoj": defs_dict,
    }
    if uuid:
        data["uuid"] = uuid

    node = node_svc.create(data)
    node_uuid = node["uuid"]

    # Build arcs from shortcuts
    arcs: list[dict] = []
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Ensure rdf:type, rdfs:subClassOf, owl:disjointWith, owl:inverseOf exist as predicates
    _ensure_predicate(pred_svc, "rdf:type", "type")
    _ensure_predicate(pred_svc, "rdfs:subClassOf", "subClassOf")
    _ensure_predicate(pred_svc, "owl:disjointWith", "disjointWith")
    _ensure_predicate(pred_svc, "owl:inverseOf", "inverseOf")

    for t in (tipo or []):
        try:
            target = node_svc.resolve_uuid_prefix(t)
            if target:
                arcs.append({
                    "subject": node_uuid, "predicate": "rdf:type",
                    "object": target["uuid"], "object_type": "uri",
                })
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua tipo-prefikso: {e}", "Ambiguous type prefix: {e}", "Préfixe type ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1)
    for s in (superklaso or []):
        try:
            target = node_svc.resolve_uuid_prefix(s)
            if target:
                arcs.append({
                    "subject": node_uuid, "predicate": "rdfs:subClassOf",
                    "object": target["uuid"], "object_type": "uri",
                })
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua superklaso-prefikso: {e}", "Ambiguous superclass prefix: {e}", "Préfixe superclasse ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1)
    for n in (ne or []):
        try:
            target = node_svc.resolve_uuid_prefix(n)
            if target:
                arcs.append({
                    "subject": node_uuid, "predicate": "owl:disjointWith",
                    "object": target["uuid"], "object_type": "uri",
                })
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua malakorda-prefikso: {e}", "Ambiguous disjoint prefix: {e}", "Préfixe disjoint ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1)
    for inv in (invers or []):
        try:
            target = node_svc.resolve_uuid_prefix(inv)
            if target:
                arcs.append({
                    "subject": node_uuid, "predicate": "owl:inverseOf",
                    "object": target["uuid"], "object_type": "uri",
                })
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua inversa-prefikso: {e}", "Ambiguous inverse prefix: {e}", "Préfixe inverse ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1)

    # Show preview and confirm
    if arcs:
        label = resolve_node_label(node_svc, node_uuid)
        if not confirm_node_with_arcs(node_svc, pred_svc, label, node_uuid, arcs, yes=yes):
            # Rollback: delete the node
            node_svc.delete(node_uuid)
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

        for arc in arcs:
            try:
                triple_svc.add(
                    subject_uuid=arc["subject"],
                    predicate_id=arc["predicate"],
                    object_value=arc["object"],
                    object_type=arc["object_type"],
                )
            except ValueError:
                pass  # Arc may already exist
    elif not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu krei nodon {label}?",
                "Create node {label}?",
                "Créer le nœud {label}?",
            ).format(label=resolve_node_label(node_svc, node_uuid)),
            default=True,
        ):
            node_svc.delete(node_uuid)
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    info(tr_multi(
        "Nodo kreita: {label} ({uuid})",
        "Node created: {label} ({uuid})",
        "Nœud créé : {label} ({uuid})",
    ).format(label=resolve_node_label(node_svc, node_uuid), uuid=node_uuid[:8]))


@nodo_app.command("modifi")
def modifi(
    uuid: str = typer.Argument(..., help=tr_multi("Nodo UUID-prefikso", "Node UUID prefix", "Préfixe UUID du nœud")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANG::TEKSTO", "Label as LANG::TEXT", "Étiquette au format LANG::TEXTE")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino en formo LANG::TEKSTO", "Definition as LANG::TEXT", "Définition au format LANG::TEXTE")),
    yes: bool = typer.Option(False, "-y", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Modifi nodon."""
    node_svc = get_node_service()
    try:
        node = node_svc.resolve_uuid_prefix(uuid)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua prefikso: {e}", "Ambiguous prefix: {e}", "Préfixe ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1)
    if not node:
        error(tr_multi("Nodo ne trovita: {u}", "Node not found: {u}", "Nœud non trouvé : {u}").format(u=uuid))
        raise typer.Exit(1)

    updates: dict = {}
    if etikedoj:
        labels: dict[str, str] = {}
        for e in etikedoj:
            if "::" in e:
                lang, _, text = e.partition("::")
                labels[lang] = text
        updates["etikedoj"] = labels
    if difinoj:
        defs: dict[str, str] = {}
        for d in difinoj:
            if "::" in d:
                lang, _, text = d.partition("::")
                defs[lang] = text
        updates["difinoj"] = defs

    if not updates:
        error(tr_multi("Neniu ŝanĝo specifita.", "No changes specified.", "Aucun changement spécifié."))
        raise typer.Exit(1)

    if not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu modifi nodon {u}?",
                "Modify node {u}?",
                "Modifier le nœud {u}?",
            ).format(u=node["uuid"][:8]),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    updated = node_svc.update(node["uuid"], updates)
    info(tr_multi("Nodo modifita: {u}", "Node modified: {u}", "Nœud modifié : {u}").format(u=updated["uuid"][:8]))


@nodo_app.command("forigi")
def forigi(
    uuid: str = typer.Argument(..., help=tr_multi("Nodo UUID-prefikso", "Node UUID prefix", "Préfixe UUID du nœud")),
    yes: bool = typer.Option(False, "-y", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Forigi nodon."""
    node_svc = get_node_service()
    try:
        node = node_svc.resolve_uuid_prefix(uuid)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua prefikso: {e}", "Ambiguous prefix: {e}", "Préfixe ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1)
    if not node:
        error(tr_multi("Nodo ne trovita: {u}", "Node not found: {u}", "Nœud non trouvé : {u}").format(u=uuid))
        raise typer.Exit(1)

    if not yes:
        label = resolve_node_label(node_svc, node["uuid"])
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                f"Ĉu forigi nodon {label} ({node['uuid'][:8]})?",
                f"Delete node {label} ({node['uuid'][:8]})?",
                f"Supprimer le nœud {label} ({node['uuid'][:8]})?",
            ),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    try:
        node_svc.delete(node["uuid"])
        info(tr_multi("Nodo forigita.", "Node deleted.", "Nœud supprimé."))
    except Exception as e:
        error(tr_multi("Foriga eraro: {e}", "Delete error: {e}", "Erreur de suppression : {e}").format(e=str(e)))
        raise typer.Exit(1) from e


@nodo_app.command("serci")
def serci(
    query: str = typer.Argument(..., help=tr_multi("Serĉa teksto", "Search text", "Texte de recherche")),
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
) -> None:
    """Serĉi nodojn per teksto (FTS5)."""
    node_svc = get_node_service()
    results = node_svc.search(query, limit=limit)

    if not results:
        info(tr_multi("Neniuj nodoj trovitaj.", "No nodes found.", "Aucun nœud trouvé."))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("UUID", no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)

    for n in results:
        try:
            labels = json.loads(n["etikedoj"])
            label = labels.get("eo") or labels.get("en") or ""
        except (json.JSONDecodeError, TypeError):
            label = ""
        table.add_row(n["uuid"][:8], label)

    info(table)


def _ensure_predicate(pred_svc, predicate_id: str, label_eo: str) -> None:
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
            "label_eo": label_eo,
            "source": "rdf",
        })
    except ValueError as e:
        # Only ignore duplicate key errors (race condition from concurrent create)
        if "UNIQUE constraint failed" not in str(e) and "already exists" not in str(e):
            # Re-raise other errors (validation, FK, etc.)
            raise
