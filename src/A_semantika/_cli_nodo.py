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
    table.add_column("ID", no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)

    for n in nodes:
        try:
            labels = json.loads(n["etikedoj"])
            label = labels.get("eo") or labels.get("en") or ""
        except (json.JSONDecodeError, TypeError):
            label = ""
        table.add_row(n["node_id"][:8], label)

    info(table)


@nodo_app.command("vidi")
def vidi(
    node_id: str = typer.Argument(..., help=tr_multi("Nod-indekso", "Node ID", "ID du nœud")),
) -> None:
    """Vidi detalojn de nodo."""
    node_svc = get_node_service()
    try:
        node = node_svc.resolve_uuid_prefix(node_id)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua prefikso: {e}", "Ambiguous prefix: {e}", "Préfixe ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1)
    if not node:
        error(tr_multi("Nodo ne trovita: {u}", "Node not found: {u}", "Nœud non trouvé : {u}").format(u=node_id))
        raise typer.Exit(1)

    try:
        labels = json.loads(node["etikedoj"])
        defns = json.loads(node["difinoj"])
    except (json.JSONDecodeError, TypeError):
        labels = {}
        defns = {}

    info(tr_multi("UUID: {u}", "UUID: {u}", "UUID : {u}").format(u=node["node_id"]))
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
    node_id: Optional[str] = typer.Argument(None, help=tr_multi("Indekso (malplena = aŭtomata)", "ID (empty = auto-generate)", "ID (vide = auto-généré)")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANG::TEKSTO", "Label as LANG::TEXT", "Étiquette au format LANG::TEXTE")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino en formo LANG::TEKSTO", "Definition as LANG::TEXT", "Définition au format LANG::TEXTE")),
    tipo: Optional[list[str]] = typer.Option(None, "-t", "--tipo", help=tr_multi("Tipo (rdf:type) nod-indekso", "Type (rdf:type) node ID", "Type (rdf:type) ID du nœud")),
    superklaso: Optional[list[str]] = typer.Option(None, "-so", "--superklaso", help=tr_multi("Superklaso (rdfs:subClassOf) nod-indekso", "Superclass (rdfs:subClassOf) node ID", "Superclasse (rdfs:subClassOf) ID du nœud")),
    ne: Optional[list[str]] = typer.Option(None, "--ne", help=tr_multi("Malakorda (owl:disjointWith) nod-indekso", "Disjoint (owl:disjointWith) node ID", "Disjoint (owl:disjointWith) ID du nœud")),
    invers: Optional[list[str]] = typer.Option(None, "--invers", "-iv", help=tr_multi("Inversa (owl:inverseOf) nod-indekso", "Inverse (owl:inverseOf) node ID", "Inverse (owl:inverseOf) ID du nœud")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
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
    if node_id:
        data["node_id"] = node_id

    try:
        node = node_svc.create(data)
    except ValueError as e:
        error(str(e))
        raise typer.Exit(1)
    node_id_val = node["node_id"]

    # Build arcs from shortcuts
    arcs: list[dict] = []
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Safety net: these predicates are seeded in init_db() via
    # DEFAULT_PREDICATES in storage.py, but _ensure_predicate is kept
    # for backward compat with databases created before seeding was added.
    _ensure_predicate(pred_svc, "rdf:type", "type")
    _ensure_predicate(pred_svc, "rdfs:subClassOf", "subClassOf")
    _ensure_predicate(pred_svc, "owl:disjointWith", "disjointWith")
    _ensure_predicate(pred_svc, "owl:inverseOf", "inverseOf")

    for t in (tipo or []):
        try:
            target = node_svc.resolve_uuid_prefix(t)
            if target:
                arcs.append({
                    "subject": node_id_val, "predicate": "rdf:type",
                    "object": target["node_id"], "object_type": "uri",
                })
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua tipo-prefikso: {e}", "Ambiguous type prefix: {e}", "Préfixe type ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1)
    for s in (superklaso or []):
        try:
            target = node_svc.resolve_uuid_prefix(s)
            if target:
                arcs.append({
                    "subject": node_id_val, "predicate": "rdfs:subClassOf",
                    "object": target["node_id"], "object_type": "uri",
                })
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua superklaso-prefikso: {e}", "Ambiguous superclass prefix: {e}", "Préfixe superclasse ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1)
    for n in (ne or []):
        try:
            target = node_svc.resolve_uuid_prefix(n)
            if target:
                arcs.append({
                    "subject": node_id_val, "predicate": "owl:disjointWith",
                    "object": target["node_id"], "object_type": "uri",
                })
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua malakorda-prefikso: {e}", "Ambiguous disjoint prefix: {e}", "Préfixe disjoint ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1)
    for inv in (invers or []):
        try:
            target = node_svc.resolve_uuid_prefix(inv)
            if target:
                arcs.append({
                    "subject": node_id_val, "predicate": "owl:inverseOf",
                    "object": target["node_id"], "object_type": "uri",
                })
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua inversa-prefikso: {e}", "Ambiguous inverse prefix: {e}", "Préfixe inverse ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1)

    # Show preview and confirm
    if arcs:
        label = resolve_node_label(node_svc, node_id_val)
        if not confirm_node_with_arcs(node_svc, pred_svc, label, node_id_val, arcs, yes=yes):
            # Rollback: delete the node
            node_svc.delete(node_id_val)
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
            except ValueError as e:
                # Only suppress "already exists" — re-raise other errors
                if "already exists" not in str(e):
                    raise
    elif not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu krei nodon {label}?",
                "Create node {label}?",
                "Créer le nœud {label}?",
            ).format(label=resolve_node_label(node_svc, node_id_val)),
            default=True,
        ):
            node_svc.delete(node_id_val)
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    info(tr_multi(
        "Nodo kreita: {label} ({node_id})",
        "Node created: {label} ({node_id})",
        "Nœud créé : {label} ({node_id})",
    ).format(label=resolve_node_label(node_svc, node_id_val), node_id=node_id_val[:8]))


@nodo_app.command("modifi")
def modifi(
    node_id: str = typer.Argument(..., help=tr_multi("Nod-indekso", "Node ID", "ID du nœud")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANG::TEKSTO", "Label as LANG::TEXT", "Étiquette au format LANG::TEXTE")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino en formo LANG::TEKSTO", "Definition as LANG::TEXT", "Définition au format LANG::TEXTE")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Modifi nodon."""
    node_svc = get_node_service()
    try:
        node = node_svc.resolve_uuid_prefix(node_id)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua prefikso: {e}", "Ambiguous prefix: {e}", "Préfixe ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1)
    if not node:
        error(tr_multi("Nodo ne trovita: {u}", "Node not found: {u}", "Nœud non trouvé : {u}").format(u=node_id))
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
            ).format(u=node["node_id"][:8]),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    updated = node_svc.update(node["node_id"], updates)
    info(tr_multi("Nodo modifita: {u}", "Node modified: {u}", "Nœud modifié : {u}").format(u=updated["node_id"][:8]))


@nodo_app.command("forigi")
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

    # Phase 1: Resolve all identifiers
    resolved: list[dict] = []
    errors: list[tuple[str, str]] = []

    for nid in node_ids:
        try:
            node = node_svc.resolve_uuid_prefix(nid)
            if node:
                resolved.append(node)
            else:
                errors.append((nid, tr_multi("ne trovita", "not found", "non trouvé")))
        except AmbiguousUUIDError:
            errors.append((nid, tr_multi("ambigua prefikso", "ambiguous prefix", "préfixe ambigu")))

    # Report resolution errors
    for input_val, reason in errors:
        error(tr_multi(
            "Forigi {i}: {r}", "Delete {i}: {r}", "Supprimer {i} : {r}",
        ).format(i=input_val, r=reason))

    if not resolved:
        error(tr_multi("Nenio forigebla.", "Nothing to delete.", "Rien à supprimer."))
        raise typer.Exit(1)

    # Phase 2: Batch preview and confirmation
    # Single-item deletion skips confirmation (user already specified exact item)
    if not yes and len(resolved) >= 2:
        table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
        table.add_column("ID", no_wrap=True)
        table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)

        for node in resolved:
            label = resolve_node_label(node_svc, node["node_id"])
            table.add_row(node["node_id"][:8], label)
        info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu forigi {n} nodojn?", "Delete {n} nodes?", "Supprimer {n} nœuds?",
            ).format(n=len(resolved)),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Phase 3: Delete each resolved node
    deleted = 0
    for node in resolved:
        try:
            node_svc.delete(node["node_id"])
            deleted += 1
        except Exception as e:
            err_msg = str(e)
            if "UNIQUE constraint failed" in err_msg:
                err_msg = tr_multi(
                    "Nodo {u} jam estas en la rubujo.",
                    "Node {u} is already in the trash.",
                    "Le nœud {u} est déjà dans la corbeille.",
                ).format(u=node["node_id"][:8])
            error(tr_multi(
                "Eraro forigante {u}: {e}",
                "Error deleting {u}: {e}",
                "Erreur lors de la suppression de {u} : {e}",
            ).format(u=node["node_id"][:8], e=err_msg))

    info(tr_multi(
        "Forigis {d} el {t} nodoj.",
        "Deleted {d} of {t} nodes.",
        "Supprimé {d} sur {t} nœuds.",
    ).format(d=deleted, t=len(resolved)))


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
        table.add_row(n["node_id"][:8], label)

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
            "etikedoj": {"eo": label_eo},
            "source": "rdf",
        })
    except ValueError as e:
        # Only ignore duplicate key errors (race condition from concurrent create)
        if "UNIQUE constraint failed" not in str(e) and "already exists" not in str(e):
            # Re-raise other errors (validation, FK, etc.)
            raise
