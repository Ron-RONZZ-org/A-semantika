"""Nodo subcommand group CLI: ls, vidi, aldoni, modifi, forigi, serci.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika._cli_helpers import (
    create_node_arcs,
    ensure_predicate,
    parse_lang_tag_pairs,
    resolve_arc_targets,
)
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import (
    build_node_modify_preview,
    confirm_node_creation,
    confirm_node_with_arcs,
    resolve_node_label,
)
from A_semantika.data.storage import label_from_json
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
    labels_dict = parse_lang_tag_pairs(etikedoj)
    defs_dict = parse_lang_tag_pairs(difinoj)

    data: dict = {
        "etikedoj": labels_dict,
        "difinoj": defs_dict,
    }
    if node_id:
        data["node_id"] = node_id

    # Pre-resolve arc target nodes before creating the subject node,
    # so ambiguous/not-found errors don't leave orphan nodes.
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Safety net: these predicates are seeded in init_db() via
    # DEFAULT_PREDICATES in storage.py, but _ensure_predicate is kept
    # for backward compat with databases created before seeding was added.
    ensure_predicate(pred_svc, "rdf:type", "type")
    ensure_predicate(pred_svc, "rdfs:subClassOf", "subClassOf")
    ensure_predicate(pred_svc, "owl:disjointWith", "disjointWith")
    ensure_predicate(pred_svc, "owl:inverseOf", "inverseOf")

    arc_templates, arc_errors = resolve_arc_targets(
        node_svc, tipo, superklaso, ne, invers,
    )

    if arc_errors:
        for msg in arc_errors:
            error(msg)
        raise typer.Exit(1)

    # ---- Duplicate detection: if node_id provided and node exists, propose update ----
    existing_node: dict[str, Any] | None = None
    if node_id:
        try:
            existing_node = node_svc.resolve_node_id_prefix(node_id)
        except AmbiguousUUIDError:
            # Ambiguous prefix — let create() raise the IntegrityError naturally
            existing_node = None

    if existing_node is not None:
        # Parse existing labels/definitions
        try:
            old_labels = json.loads(existing_node.get("etikedoj", "{}"))
        except (json.JSONDecodeError, TypeError):
            old_labels = {}
        try:
            old_defns = json.loads(existing_node.get("difinoj", "{}"))
        except (json.JSONDecodeError, TypeError):
            old_defns = {}
        if not isinstance(old_labels, dict):
            old_labels = {}
        if not isinstance(old_defns, dict):
            old_defns = {}

        # Merge new values into existing (same as modifi merge mode)
        new_labels = dict(old_labels)
        new_labels.update(labels_dict)
        new_defns = dict(old_defns)
        new_defns.update(defs_dict)

        ex_id = existing_node["node_id"]
        noop = (new_labels == old_labels and new_defns == old_defns)

        if noop and not arc_templates:
            info(tr_multi(
                "Nodo {u} jam ekzistas kaj estas identa.",
                "Node {u} already exists and is identical.",
                "Le nœud {u} existe déjà et est identique.",
            ).format(u=ex_id[:16]))
            return

        # Show diff preview before confirming
        if not yes:
            table = build_node_modify_preview(
                ex_id, old_labels, new_labels, old_defns, new_defns,
            )
            if table:
                info("")
                info(table)

            from A.utils.interactive import confirm_action

            confirm_msg = tr_multi(
                "Nodo {u} jam ekzistas. Ĉu ĝisdatigi?",
                "Node {u} already exists. Update?",
                "Le nœud {u} existe déjà. Mettre à jour ?",
            ).format(u=ex_id[:16])
            if not confirm_action(confirm_msg, default=True):
                info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
                raise typer.Exit(0)

        # Apply updates
        updates: dict[str, Any] = {}
        if new_labels != old_labels:
            updates["etikedoj"] = new_labels
        if new_defns != old_defns:
            updates["difinoj"] = new_defns
        if updates:
            node_svc.update(ex_id, updates)

        # Handle arcs on the existing node
        if arc_templates:
            arcs: list[dict[str, Any]] = [
                {"subject": ex_id, "predicate": pred, "object": target_id, "object_type": "uri"}
                for target_id, pred in arc_templates
            ]
            label = resolve_node_label(node_svc, ex_id)
            if not confirm_node_with_arcs(node_svc, pred_svc, label, ex_id, arcs, yes=yes):
                info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
                raise typer.Exit(0)
            try:
                create_node_arcs(triple_svc, node_svc, ex_id, arcs)
            except ValueError as e:
                error(str(e))
                raise typer.Exit(1) from e

        info(tr_multi(
            "Nodo ĝisdatigita: {label} ({node_id})",
            "Node updated: {label} ({node_id})",
            "Nœud mis à jour : {label} ({node_id})",
        ).format(label=resolve_node_label(node_svc, ex_id), node_id=ex_id[:16]))
        return

    # ---- No duplicate — normal creation path ----
    try:
        node = node_svc.create(data)
    except ValueError as e:
        error(str(e))
        raise typer.Exit(1) from e
    node_id_val = node["node_id"]

    # Build full arc dicts with the now-known subject node_id
    arcs: list[dict] = [
        {"subject": node_id_val, "predicate": pred, "object": target_id, "object_type": "uri"}
        for target_id, pred in arc_templates
    ]

    # Show preview and confirm
    if arcs:
        label = resolve_node_label(node_svc, node_id_val)
        if not confirm_node_with_arcs(node_svc, pred_svc, label, node_id_val, arcs, yes=yes):
            # Rollback: delete the node
            node_svc.delete(node_id_val)
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

        try:
            create_node_arcs(triple_svc, node_svc, node_id_val, arcs)
        except ValueError as e:
            error(str(e))
            raise typer.Exit(1) from e
    elif not confirm_node_creation(node_id_val, labels_dict, defs_dict, yes=yes):
        node_svc.delete(node_id_val)
        info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
        raise typer.Exit(0)

    info(tr_multi(
        "Nodo kreita: {label} ({node_id})",
        "Node created: {label} ({node_id})",
        "Nœud créé : {label} ({node_id})",
    ).format(label=resolve_node_label(node_svc, node_id_val), node_id=node_id_val[:16]))


@nodo_app.command("modifi")
def modifi(
    node_id: str = typer.Argument(..., help=tr_multi("Nod-indekso", "Node ID", "ID du nœud")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANG::TEKSTO", "Label as LANG::TEXT", "Étiquette au format LANG::TEXTE")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino en formo LANG::TEKSTO", "Definition as LANG::TEXT", "Définition au format LANG::TEXTE")),
    anstatauigi: bool = typer.Option(False, "-r", "--anstatauigi", help=tr_multi("Anstataŭigi anstataŭ kunfandi etikedojn/difinojn", "Replace instead of merging labels/definitions", "Remplacer au lieu de fusionner les étiquettes/définitions")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Modifi nodon.

    Defaŭlte -e kaj -d KUNFANDAS novajn valorojn kun ekzistantaj (aldonas/ĝisdatigas).
    Uzu -r por ANSTATAŬIGI (forigi ĉiujn ekzistantajn kaj uzi nur la specifitajn).

    Ekzemploj:
      nodo modifi TERO -e eo::Tero          # aldoni/ĝisdatigi esperantan etikedon
      nodo modifi TERO -e eo::Tero -r       # anstataŭigi per nur esperanta
    """
    node_svc = get_node_service()
    try:
        node = node_svc.resolve_node_id_prefix(node_id)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua prefikso: {e}", "Ambiguous prefix: {e}", "Préfixe ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not node:
        error(tr_multi("Nodo ne trovita: {u}", "Node not found: {u}", "Nœud non trouvé : {u}").format(u=node_id))
        raise typer.Exit(1)

    # Parse existing values
    try:
        old_labels = json.loads(node.get("etikedoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_labels = {}
    try:
        old_defns = json.loads(node.get("difinoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_defns = {}

    updates: dict = {}
    new_labels: dict[str, str] | None = None
    new_defns: dict[str, str] | None = None

    if etikedoj:
        parsed_labels = parse_lang_tag_pairs(etikedoj)
        if anstatauigi:
            new_labels = dict(parsed_labels)
        else:
            new_labels = dict(old_labels)
            new_labels.update(parsed_labels)
        updates["etikedoj"] = new_labels

    if difinoj:
        parsed_defns = parse_lang_tag_pairs(difinoj)
        if anstatauigi:
            new_defns = dict(parsed_defns)
        else:
            new_defns = dict(old_defns)
            new_defns.update(parsed_defns)
        updates["difinoj"] = new_defns

    if not updates:
        error(tr_multi("Neniu ŝanĝo specifita.", "No changes specified.", "Aucun changement spécifié."))
        raise typer.Exit(1)

    # No-op detection: compare old vs new
    noop = (
        (new_labels is None or new_labels == old_labels)
        and (new_defns is None or new_defns == old_defns)
    )
    if noop:
        info(tr_multi(
            "Neniu ŝanĝo: nodo restas neŝanĝita.",
            "No change: node remains unchanged.",
            "Aucun changement : le nœud reste inchangé.",
        ))
        return

    # Show change summary and confirm
    if not yes:
        table = build_node_modify_preview(
            node["node_id"],
            old_labels, new_labels,
            old_defns, new_defns,
        )
        if table:
            info("")
            info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu modifi nodon {u}?",
                "Modify node {u}?",
                "Modifier le nœud {u}?",
            ).format(u=node["node_id"][:16]),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    updated = node_svc.update(node["node_id"], updates)
    info(tr_multi("Nodo modifita: {u}", "Node modified: {u}", "Nœud modifié : {u}").format(u=updated["node_id"][:16]))





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
    """Serĉi nodojn per teksto (FTS5)."""
    node_svc = get_node_service()
    results = node_svc.search(query, limit=limit)

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


# Side-effect import: registers the ``forigi`` command on ``nodo_app``.
# Must be after all other functions (``nodo_app`` must exist first).
from A_semantika import _cli_nodo_forigi  # noqa: E402, F401
