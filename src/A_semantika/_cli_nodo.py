"""Nodo subcommand group CLI: ls, vidi, aldoni, modifi, forigi, serci.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._cli_helpers import create_node_arcs, ensure_predicate, resolve_arc_targets
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import (
    build_node_modify_preview,
    confirm_node_creation,
    confirm_node_with_arcs,
    resolve_node_label,
    resolve_predicate_label,
)
from A_semantika.data.storage import label_from_json
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
    labels_dict: dict[str, str] = {}
    defs_dict: dict[str, str] = {}
    if etikedoj:
        for e in etikedoj:
            if "::" in e:
                lang, _, text = e.partition("::")
            elif ":" in e:
                lang, _, text = e.partition(":")
            else:
                warning(tr_multi(
                    "Nevalida etikedo-formato (mankas ':' aŭ '::'): {i}",
                    "Invalid label format (missing ':' or '::'): {i}",
                    "Format d'étiquette invalide (' : ' ou ' :: ' manquant) : {i}",
                ).format(i=e))
                continue
            if lang and text:
                labels_dict[lang] = text
            else:
                warning(tr_multi(
                    "Malplena lingvokodo aŭ teksto en: {i}",
                    "Empty language code or text in: {i}",
                    "Code de langue ou texte vide dans : {i}",
                ).format(i=e))
    if difinoj:
        for d in difinoj:
            if "::" in d:
                lang, _, text = d.partition("::")
            elif ":" in d:
                lang, _, text = d.partition(":")
            else:
                warning(tr_multi(
                    "Nevalida difino-formato (mankas ':' aŭ '::'): {i}",
                    "Invalid definition format (missing ':' or '::'): {i}",
                    "Format de définition invalide (' : ' ou ' :: ' manquant) : {i}",
                ).format(i=d))
                continue
            if lang and text:
                defs_dict[lang] = text
            else:
                warning(tr_multi(
                    "Malplena lingvokodo aŭ teksto en: {i}",
                    "Empty language code or text in: {i}",
                    "Code de langue ou texte vide dans : {i}",
                ).format(i=d))

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

    # Now create the subject node (safe — all targets resolved successfully)
    try:
        node = node_svc.create(data)
    except ValueError as e:
        err_str = str(e)
        # If node_id was provided and already exists, propose to update instead
        if node_id and "already exists" in err_str:
            existing = node_svc.get(node_id)
            if existing:
                existing_label = resolve_node_label(node_svc, node_id)
                info(tr_multi(
                    "Nodo {label} ({node_id}) jam ekzistas.",
                    "Node {label} ({node_id}) already exists.",
                    "Le nœud {label} ({node_id}) existe déjà.",
                ).format(label=existing_label, node_id=node_id[:16]))
                if not yes:
                    msg = tr_multi(
                        "Ĉu vi volas ĝisdatigi ĝin kun la novaj etikedoj/difinoj?",
                        "Do you want to update it with the new labels/definitions?",
                        "Voulez-vous le mettre à jour avec les nouvelles étiquettes/définitions ?",
                    )
                    if confirm_action(msg, default=False):
                        update_data: dict[str, Any] = {}
                        if labels_dict:
                            update_data["etikedoj"] = labels_dict
                        if defs_dict:
                            update_data["difinoj"] = defs_dict
                        if update_data:
                            node_svc.update(node_id, update_data)
                        info(tr_multi(
                            "Nodo ĝisdatigita: {label} ({node_id})",
                            "Node updated: {label} ({node_id})",
                            "Nœud mis à jour : {label} ({node_id})",
                        ).format(
                            label=resolve_node_label(node_svc, node_id),
                            node_id=node_id[:16],
                        ))
                        raise typer.Exit(0)
                else:
                    # -y mode: silently exit
                    raise typer.Exit(0)
        error(err_str)
        raise typer.Exit(1) from e
    node_id_val = node["node_id"]

    # Check for duplicate: if node has labels, search for similar existing nodes
    if labels_dict:
        # Try to find existing node with same labels (using FTS search on first label)
        eo_label = labels_dict.get("eo") or next(iter(labels_dict.values()), None)
        if eo_label:
            # Use AND matching for duplicate detection: require ALL query words
            # to appear in the matched node's label_text. OR-based FTS (used by
            # node_svc.search) is too broad — "genetika algoritmo" should not
            # match a node with label "Algoritmo" alone.
            candidates = node_svc.search(eo_label, limit=10)
            query_words = set(eo_label.lower().split())
            similar = None
            for c in candidates:
                if c["node_id"] == node_id_val:
                    continue
                label_words = set(c.get("label_text", "").lower().split())
                if query_words.issubset(label_words):
                    similar = c
                    break
            if similar:
                existing_id = similar["node_id"]
                existing_label = resolve_node_label(node_svc, existing_id)
                info(tr_multi(
                    "Simila nodo jam ekzistas: {label} ({node_id})",
                    "Similar node already exists: {label} ({node_id})",
                    "Un nœud similaire existe déjà : {label} ({node_id})",
                ).format(label=existing_label, node_id=existing_id[:16]))
                # Only auto-prompt if not in skip-confirmation mode (-y)
                if not yes:
                    msg = tr_multi(
                        "Ĉu ĝi estas la sama nodo?",
                        "Is it the same node?",
                        "Est-ce le même nœud ?",
                    )
                    if confirm_action(msg, default=False):
                        # User wants to update existing node instead
                        node_svc.delete(node_id_val)
                        info(tr_multi(
                            "Novnodo ne kreita. Uzu 'A semantika nodo modifi' por ĝisdatigi.",
                            "New node not created. Use 'A semantika nodo modifi' to update it.",
                            "Nouveau nœud non créé. Utilisez 'A semantika nodo modifi' pour le mettre à jour.",
                        ))
                        raise typer.Exit(0)

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


def _parse_lang_tag_pairs(items: list[str]) -> dict[str, str]:
    """Parse ``LANG::TEKSTO`` or ``LANG:TEKSTO`` list into a dict.

    Warns about malformed entries (no separator).
    Strips leading/trailing whitespace from lang and text.
    """
    result: dict[str, str] = {}
    for item in items:
        if "::" in item:
            lang, _, text = item.partition("::")
        elif ":" in item:
            lang, _, text = item.partition(":")
        else:
            warning(tr_multi(
                "Nevalida etikedo-formato (mankas ':' aŭ '::'): {i}",
                "Invalid label format (missing ':' or '::'): {i}",
                "Format d'étiquette invalide (' : ' ou ' :: ' manquant) : {i}",
            ).format(i=item))
            continue
        # Strip whitespace from both language code and text
        lang = lang.strip()
        text = text.strip()
        if lang and text:
            result[lang] = text
        else:
            warning(tr_multi(
                "Malplena lingvokodo aŭ teksto en: {i}",
                "Empty language code or text in: {i}",
                "Code de langue ou texte vide dans : {i}",
            ).format(i=item))
    return result


@nodo_app.command("modifi")
def modifi(
    node_id: str = typer.Argument(..., help=tr_multi("Nod-indekso", "Node ID", "ID du nœud")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANG::TEKSTO", "Label as LANG::TEXT", "Étiquette au format LANG::TEXTE")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino en formo LANG::TEKSTO", "Definition as LANG::TEXT", "Définition au format LANG::TEXTE")),
    nova_id: Optional[str] = typer.Option(None, "--nova-id", "-ni", help=tr_multi("Nova nod-indekso (renomi)", "New node ID (rename)", "Nouvel ID du nœud (renommer)")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Modifi nodon."""
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
        parsed_labels = _parse_lang_tag_pairs(etikedoj)
        new_labels = dict(old_labels)
        new_labels.update(parsed_labels)
        updates["etikedoj"] = new_labels

    if difinoj:
        parsed_defns = _parse_lang_tag_pairs(difinoj)
        new_defns = dict(old_defns)
        new_defns.update(parsed_defns)
        updates["difinoj"] = new_defns

    # Handle no-op for --nova-id: same as current ID
    if nova_id and nova_id == node["node_id"]:
        nova_id = None

    if not updates and not nova_id:
        error(tr_multi("Neniu ŝanĝo specifita.", "No changes specified.", "Aucun changement spécifié."))
        raise typer.Exit(1)

    # No-op detection: compare old vs new
    noop = (
        (new_labels is None or new_labels == old_labels)
        and (new_defns is None or new_defns == old_defns)
        and nova_id is None
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

    try:
        if nova_id:
            updated = node_svc.update_node_id(node["node_id"], nova_id, updates)
            current_id = updated["node_id"]
            info(tr_multi(
                "Nodo renomita: {old} → {new}",
                "Node renamed: {old} → {new}",
                "Nœud renommé : {old} → {new}",
            ).format(old=node["node_id"][:16], new=current_id[:16]))
        else:
            updated = node_svc.update(node["node_id"], updates)
            current_id = updated["node_id"]
            info(tr_multi("Nodo modifita: {u}", "Node modified: {u}", "Nœud modifié : {u}").format(u=current_id[:16]))
    except ValueError as e:
        error(str(e))
        raise typer.Exit(1) from e


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
