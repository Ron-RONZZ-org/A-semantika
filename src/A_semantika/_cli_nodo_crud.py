"""Nodo CRUD subcommand group: aldoni, modifi."""
from __future__ import annotations

import json
from typing import Any, Optional

import typer

from A import copy_to_clipboard, error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._cli_arc_helpers import create_node_arcs, resolve_arc_targets
from A_semantika._cli_helpers import ensure_predicate
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import (
    build_node_modify_preview,
    confirm_node_creation,
    confirm_node_with_arcs,
    resolve_node_label,
)
from A_semantika.service import get_node_service, get_predicate_service, get_triple_service


def _parse_lang_tag_pairs(items: list[str]) -> dict[str, str]:
    """Parse ``LANG::TEKSTO``, ``LANG:TEKSTO``, or plain text list into a dict.

    When a colon separator (``::`` or ``:``) is present, splits into
    language code and text.  When no separator is found, the full text
    is treated as a **language-independent** label (stored with an empty
    string key).

    Strips leading/trailing whitespace from lang and text.
    """
    result: dict[str, str] = {}
    for item in items:
        if "::" in item:
            lang, _, text = item.partition("::")
        elif ":" in item:
            lang, _, text = item.partition(":")
        else:
            # No separator → language-independent label
            text = item.strip()
            if text:
                result[""] = text
            else:
                warning(tr_multi(
                    "Malplena etikedo: {i}",
                    "Empty label: {i}",
                    "Étiquette vide : {i}",
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


def aldoni(
    node_id: Optional[str] = typer.Argument(None, help=tr_multi("Indekso (malplena = aŭtomata)", "ID (empty = auto-generate)", "ID (vide = auto-généré)")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo: LANG::TEKSTO aŭ simple TEKSTO (senlingva)", "Label as LANG::TEXT or plain TEXT (language-independent)", "Étiquette : LANG::TEXTE ou TEXTE simple (indépendant de la langue)")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino: LANG::TEKSTO aŭ simple TEKSTO (senlingva)", "Definition as LANG::TEXT or plain TEXT (language-independent)", "Définition : LANG::TEXTE ou TEXTE simple (indépendant de la langue)")),
    tipo: Optional[list[str]] = typer.Option(None, "-t", "--tipo", help=tr_multi("Tipo (rdf:type) nod-indekso", "Type (rdf:type) node ID", "Type (rdf:type) ID du nœud")),
    superklaso: Optional[list[str]] = typer.Option(None, "-so", "--superklaso", help=tr_multi("Superklaso (rdfs:subClassOf) nod-indekso", "Superclass (rdfs:subClassOf) node ID", "Superclasse (rdfs:subClassOf) ID du nœud")),
    ne: Optional[list[str]] = typer.Option(None, "--ne", help=tr_multi("Malakorda (owl:disjointWith) nod-indekso", "Disjoint (owl:disjointWith) node ID", "Disjoint (owl:disjointWith) ID du nœud")),
    invers: Optional[list[str]] = typer.Option(None, "--invers", "-iv", help=tr_multi("Inversa (owl:inverseOf) nod-indekso", "Inverse (owl:inverseOf) node ID", "Inverse (owl:inverseOf) ID du nœud")),
    kopii: bool = typer.Option(False, "-k", "--kopii", help=tr_multi(
        "Kopii nod-indekson al poŝo",
        "Copy node ID to clipboard",
        "Copier l'ID du nœud dans le presse-papier",
    )),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi(
        "Preterpasi konfirmon",
        "Skip confirmation",
        "Ignorer la confirmation",
    )),
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
                # No separator → language-independent label
                text = e.strip()
                if text:
                    labels_dict[""] = text
                else:
                    warning(tr_multi(
                        "Malplena etikedo: {i}",
                        "Empty label: {i}",
                        "Étiquette vide : {i}",
                    ).format(i=e))
                continue
            lang = lang.strip()
            text = text.strip()
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
                # No separator → language-independent label
                text = d.strip()
                if text:
                    defs_dict[""] = text
                else:
                    warning(tr_multi(
                        "Malplena difino: {i}",
                        "Empty definition: {i}",
                        "Définition vide : {i}",
                    ).format(i=d))
                continue
            lang = lang.strip()
            text = text.strip()
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

    # Pre-build arc template list for reuse in all code paths.
    # These describe arcs to create: (target_id, predicate).
    # The subject depends on whether we're updating an existing node
    # or creating a new one, and is filled in at point of use.
    new_arc_dicts: list[dict] = [
        {"predicate": pred, "object": target_id, "object_type": "uri"}
        for target_id, pred in arc_templates
    ]

    # Helper: get existing arcs for a node (where node is subject).
    def _get_existing_arcs(nid: str) -> list[dict]:
        """Return existing arcs for *nid* (triples where *nid* is subject)."""
        all_triples = triple_svc.get_by_node(nid)
        return [
            {"predicate": t["predicate_id"], "object": t["object_value"], "object_type": t["object_type"]}
            for t in all_triples
            if t["subject_uuid"] == nid
        ]

    def _apply_update(node_to_update: str, delete_new: str | None = None) -> None:
        """Update labels/defs + arcs on *node_to_update*, optionally deleting *delete_new*."""
        update_data: dict[str, Any] = {}
        if labels_dict:
            update_data["etikedoj"] = labels_dict
        if defs_dict:
            update_data["difinoj"] = defs_dict
        if update_data:
            node_svc.update(node_to_update, update_data)
        # Create arcs on the existing node
        if new_arc_dicts:
            arcs_with_subject = [
                {"subject": node_to_update, **a}
                for a in new_arc_dicts
            ]
            create_node_arcs(triple_svc, node_svc, node_to_update, arcs_with_subject)
        if delete_new:
            node_svc.delete(delete_new)

    def _build_preview(nid: str, old_lbls: dict, new_lbls: dict | None,
                       old_dfn: dict, new_dfn: dict | None) -> tuple[Table | None, list[dict]]:
        """Build preview, also returning existing arcs for *nid*."""
        existing_arcs = _get_existing_arcs(nid)
        preview = build_node_modify_preview(
            nid, old_lbls, new_lbls,
            old_dfn, new_dfn,
            old_arcs=existing_arcs, new_arcs=new_arc_dicts or None,
        )
        return preview, existing_arcs

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
                # Parse existing labels/defs for preview
                try:
                    old_labels = json.loads(existing.get("etikedoj", "{}"))
                except (json.JSONDecodeError, TypeError):
                    old_labels = {}
                try:
                    old_defns = json.loads(existing.get("difinoj", "{}"))
                except (json.JSONDecodeError, TypeError):
                    old_defns = {}

                new_labels_for_update = labels_dict or None
                new_defns_for_update = defs_dict or None

                # Build modification preview (includes arcs if any)
                preview_table, _ = _build_preview(
                    node_id, old_labels, new_labels_for_update,
                    old_defns, new_defns_for_update,
                )

                if preview_table is None:
                    info(tr_multi(
                        "Neniu ŝanĝo: nodo {label} ({node_id}) restas neŝanĝita.",
                        "No change: node {label} ({node_id}) remains unchanged.",
                        "Aucun changement : le nœud {label} ({node_id}) reste inchangé.",
                    ).format(label=existing_label, node_id=truncate_uuid(node_id)))
                    raise typer.Exit(0)

                if not yes:
                    info(tr_multi(
                        "Nodo {label} ({node_id}) jam ekzistas.",
                        "Node {label} ({node_id}) already exists.",
                        "Le nœud {label} ({node_id}) existe déjà.",
                    ).format(label=existing_label, node_id=truncate_uuid(node_id)))
                    info("")
                    info(preview_table)
                    msg = tr_multi(
                        "Ĉu vi volas ĝisdatigi ĝin kun la supraj ŝanĝoj?",
                        "Do you want to update it with the changes above?",
                        "Voulez-vous le mettre à jour avec les modifications ci-dessus ?",
                    )
                    if confirm_action(msg, default=False):
                        _apply_update(node_id)
                        info(tr_multi(
                            "Nodo ĝisdatigita: {label} ({node_id})",
                            "Node updated: {label} ({node_id})",
                            "Nœud mis à jour : {label} ({node_id})",
                        ).format(
                            label=resolve_node_label(node_svc, node_id),
                            node_id=truncate_uuid(node_id),
                        ))
                        raise typer.Exit(0)
                    else:
                        info(tr_multi(
                            "Nuligita.",
                            "Cancelled.",
                            "Annulé.",
                        ))
                        raise typer.Exit(0)
                else:
                    # -y mode: silently update without interactive preview
                    _apply_update(node_id)
                    raise typer.Exit(0)
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=err_str))
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
                ).format(label=existing_label, node_id=truncate_uuid(existing_id)))

                # Parse existing labels/defs for preview
                try:
                    old_labels = json.loads(similar.get("etikedoj", "{}"))
                except (json.JSONDecodeError, TypeError):
                    old_labels = {}
                try:
                    old_defns = json.loads(similar.get("difinoj", "{}"))
                except (json.JSONDecodeError, TypeError):
                    old_defns = {}

                new_labels_for_update = labels_dict or None
                new_defns_for_update = defs_dict or None

                # Build modification preview (includes arcs if any)
                preview_table, _ = _build_preview(
                    existing_id, old_labels, new_labels_for_update,
                    old_defns, new_defns_for_update,
                )

                if preview_table is None:
                    # No change — delete the new node and exit
                    node_svc.delete(node_id_val)
                    info(tr_multi(
                        "Neniu ŝanĝo: nodo {label} ({node_id}) restas neŝanĝita.",
                        "No change: node {label} ({node_id}) remains unchanged.",
                        "Aucun changement : le nœud {label} ({node_id}) reste inchangé.",
                    ).format(label=existing_label, node_id=truncate_uuid(existing_id)))
                    raise typer.Exit(0)

                if not yes:
                    info("")
                    info(preview_table)
                    # Step 1: Ask if it's the same node
                    msg_same = tr_multi(
                        "Ĉu ĝi estas la sama nodo?",
                        "Is this the same node?",
                        "Est-ce le même nœud ?",
                    )
                    if confirm_action(msg_same, default=False):
                        # Step 2a: Ask whether to update
                        msg_update = tr_multi(
                            "Ĉu vi volas ĝisdatigi ĝin kun la supraj ŝanĝoj?",
                            "Do you want to update it with the changes above?",
                            "Voulez-vous le mettre à jour avec les modifications ci-dessus ?",
                        )
                        if confirm_action(msg_update, default=False):
                            _apply_update(existing_id, delete_new=node_id_val)
                            info(tr_multi(
                                "Nodo ĝisdatigita: {label} ({node_id})",
                                "Node updated: {label} ({node_id})",
                                "Nœud mis à jour : {label} ({node_id})",
                            ).format(
                                label=resolve_node_label(node_svc, existing_id),
                                node_id=truncate_uuid(existing_id),
                            ))
                            raise typer.Exit(0)
                        else:
                            node_svc.delete(node_id_val)
                            info(tr_multi(
                                "Nuligita.",
                                "Cancelled.",
                                "Annulé.",
                            ))
                            raise typer.Exit(0)
                    # User said "not the same" → fall through to creation summary
                else:
                    # -y mode: silently update existing, delete new
                    _apply_update(existing_id, delete_new=node_id_val)
                    raise typer.Exit(0)

    # Build full arc dicts with the now-known subject node_id
    arcs: list[dict] = [
        {"subject": node_id_val, "predicate": pred, "object": target_id, "object_type": "uri"}
        for target_id, pred in arc_templates
    ]

    # Show preview and confirm creation
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
            error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
            raise typer.Exit(1) from e
    elif not confirm_node_creation(node_id_val, labels_dict, defs_dict, yes=yes):
        node_svc.delete(node_id_val)
        info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
        raise typer.Exit(0)

    info(tr_multi(
        "Nodo kreita: {label} ({node_id})",
        "Node created: {label} ({node_id})",
        "Nœud créé : {label} ({node_id})",
    ).format(label=resolve_node_label(node_svc, node_id_val), node_id=truncate_uuid(node_id_val)))

    if kopii:
        if not copy_to_clipboard(node_id_val):
            warning(tr_multi(
                "Ne povis kopii al poŝo: {id}",
                "Could not copy to clipboard: {id}",
                "Impossible de copier dans le presse-papier : {id}",
            ).format(id=node_id_val))


def modifi(
    node_id: str = typer.Argument(..., help=tr_multi("Nod-indekso", "Node ID", "ID du nœud")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo: LANG::TEKSTO aŭ simple TEKSTO (senlingva)", "Label as LANG::TEXT or plain TEXT (language-independent)", "Étiquette : LANG::TEXTE ou TEXTE simple (indépendant de la langue)")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino: LANG::TEKSTO aŭ simple TEKSTO (senlingva)", "Definition as LANG::TEXT or plain TEXT (language-independent)", "Définition : LANG::TEXTE ou TEXTE simple (indépendant de la langue)")),
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
        # Fallback: substring match
        try:
            node = node_svc.resolve_node_id_substring(node_id)
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua nodo: {e}", "Ambiguous node: {e}", "Nœud ambigu : {e}").format(e=str(e)))
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
            ).format(u=truncate_uuid(node["node_id"])),
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
            ).format(old=truncate_uuid(node["node_id"]), new=truncate_uuid(current_id)))
        else:
            updated = node_svc.update(node["node_id"], updates)
            current_id = updated["node_id"]
            info(tr_multi("Nodo modifita: {u}", "Node modified: {u}", "Nœud modifié : {u}").format(u=truncate_uuid(current_id)))
    except ValueError as e:
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
