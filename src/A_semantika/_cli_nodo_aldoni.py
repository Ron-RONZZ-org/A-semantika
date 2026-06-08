"""Nodo aldoni command — node creation with auto-ID and file attachment support.

Extracted from _cli_nodo_crud.py to keep files under 500 lines.
Adds auto node_id generation from first label (Issue #74) and
``--img/--filmeto/--dosiero`` file attachment flags (Issue #75).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import typer

from A import copy_to_clipboard, error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._cli_arc_helpers import create_node_arcs, resolve_arc_targets
from A_semantika._cli_helpers import ensure_predicate
from A_semantika._file_helpers import (
    delete_file,
    handle_file_attachment,
    is_managed_file,
)
from A_semantika._node_helpers import normalize_label_to_id, truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import (
    build_node_modify_preview,
    confirm_node_creation,
    confirm_node_with_arcs,
    resolve_node_label,
)
from A_semantika.service import get_node_service, get_predicate_service, get_triple_service

# FTS5 optimize counter: trigger OPTIMIZE every N node creates to prevent
# progressive search-performance degradation from index fragmentation.
_OPTIMIZE_INTERVAL = 50
_optimize_counter: int = 0


_COLLISION_MAX = 99


def _generate_unique_node_id(base: str, node_svc: Any) -> str:
    """Return *base* if available, otherwise append ``_2``, ``_3``, etc.

    Caps retries at ``_COLLISION_MAX`` (99) then falls back to a UUID.
    """
    if not node_svc.get(base):
        return base
    for counter in range(2, _COLLISION_MAX + 1):
        candidate = f"{base}_{counter}"
        if not node_svc.get(candidate):
            return candidate
    import uuid

    return str(uuid.uuid4())


def aldoni(
    node_id: Optional[str] = typer.Argument(None, help=tr_multi(
        "Indekso (malplena = aŭtomata)", "ID (empty = auto-generate)", "ID (vide = auto-généré)",
    )),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi(
        "Etikedo: LANG::TEKSTO aŭ simple TEKSTO (senlingva)",
        "Label as LANG::TEXT or plain TEXT (language-independent)",
        "Étiquette : LANG::TEXTE ou TEXTE simple (indépendant de la langue)",
    )),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi(
        "Difino: LANG::TEKSTO aŭ simple TEKSTO (senlingva)",
        "Definition as LANG::TEXT or plain TEXT (language-independent)",
        "Définition : LANG::TEXTE ou TEXTE simple (indépendant de la langue)",
    )),
    tipo: Optional[list[str]] = typer.Option(None, "-t", "--tipo", help=tr_multi(
        "Tipo (rdf:type) nod-indekso",
        "Type (rdf:type) node ID",
        "Type (rdf:type) ID du nœud",
    )),
    superklaso: Optional[list[str]] = typer.Option(None, "-so", "--superklaso", help=tr_multi(
        "Superklaso (rdfs:subClassOf) nod-indekso",
        "Superclass (rdfs:subClassOf) node ID",
        "Superclasse (rdfs:subClassOf) ID du nœud",
    )),
    ne: Optional[list[str]] = typer.Option(None, "--ne", help=tr_multi(
        "Malakorda (owl:disjointWith) nod-indekso",
        "Disjoint (owl:disjointWith) node ID",
        "Disjoint (owl:disjointWith) ID du nœud",
    )),
    invers: Optional[list[str]] = typer.Option(None, "--invers", "-iv", help=tr_multi(
        "Inversa (owl:inverseOf) nod-indekso",
        "Inverse (owl:inverseOf) node ID",
        "Inverse (owl:inverseOf) ID du nœud",
    )),
    kopii: bool = typer.Option(False, "-k", "--kopii", help=tr_multi(
        "Kopii nod-indekson al poŝo",
        "Copy node ID to clipboard",
        "Copier l'ID du nœud dans le presse-papier",
    )),
    # File attachment flags (Issue #75)
    img: Optional[str] = typer.Option(None, "--img", "-I", help=tr_multi(
        "Aldoni bildon (dosiero aŭ URL)",
        "Attach image file (path or URL)",
        "Ajouter une image (chemin ou URL)",
    )),
    filmeto: Optional[str] = typer.Option(None, "--filmeto", "-F", help=tr_multi(
        "Aldoni filmeton (dosiero aŭ URL)",
        "Attach video file (path or URL)",
        "Ajouter une vidéo (chemin ou URL)",
    )),
    dosiero: Optional[str] = typer.Option(None, "--dosiero", "-D", help=tr_multi(
        "Aldoni ajnan dosieron (dosiero aŭ URL)",
        "Attach arbitrary file (path or URL)",
        "Ajouter un fichier (chemin ou URL)",
    )),
    en_loko: bool = typer.Option(False, "--en-loko", help=tr_multi(
        "Konservi referencon, ne kopii dosieron",
        "Store reference only, do not copy file",
        "Conserver la référence, ne pas copier le fichier",
    )),
    movi: bool = typer.Option(False, "--movi", "-m", help=tr_multi(
        "Movi dosieron anstataŭ kopii (nur loka dosiero)",
        "Move file instead of copying (local file only)",
        "Déplacer le fichier au lieu de copier (fichier local uniquement)",
    )),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi(
        "Preterpasi konfirmon",
        "Skip confirmation",
        "Ignorer la confirmation",
    )),
) -> None:
    """Aldoni novan nodon kun laŭvolaj arkoj kaj dosieraj aldonaĵoj."""
    node_svc = get_node_service()

    # ── Parse labels and definitions ─────────────────────────────────
    labels_dict: dict[str, str] = {}
    defs_dict: dict[str, str] = {}
    if etikedoj:
        for e in etikedoj:
            if "::" in e:
                lang, _, text = e.partition("::")
            elif ":" in e:
                lang, _, text = e.partition(":")
            else:
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

    # ── Auto-generate node_id from first label (Issue #74) ──────────
    if not node_id and labels_dict:
        first_val = next(v for v in labels_dict.values() if v)
        base_id = normalize_label_to_id(first_val)
        node_id = _generate_unique_node_id(base_id, node_svc)
    elif not node_id:
        # Will let NodeService.create() generate a UUID
        pass

    data: dict[str, Any] = {
        "etikedoj": labels_dict,
        "difinoj": defs_dict,
    }
    if node_id:
        data["node_id"] = node_id

    # ── Pre-resolve arc targets ─────────────────────────────────────
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

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

    new_arc_dicts: list[dict[str, Any]] = [
        {"predicate": pred, "object": target_id, "object_type": "uri"}
        for target_id, pred in arc_templates
    ]

    # ── Helper: get existing arcs for a node ─────────────────────────
    def _get_existing_arcs(nid: str) -> list[dict[str, Any]]:
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
        if new_arc_dicts:
            arcs_with_subject = [
                {"subject": node_to_update, **a}
                for a in new_arc_dicts
            ]
            create_node_arcs(triple_svc, node_svc, node_to_update, arcs_with_subject)
        if delete_new:
            node_svc.delete(delete_new)

    def _build_preview(
        nid: str, old_lbls: dict, new_lbls: dict | None,
        old_dfn: dict, new_dfn: dict | None,
    ) -> tuple[Any, list[dict[str, Any]]]:
        existing_arcs = _get_existing_arcs(nid)
        preview = build_node_modify_preview(
            nid, old_lbls, new_lbls,
            old_dfn, new_dfn,
            old_arcs=existing_arcs, new_arcs=new_arc_dicts or None,
        )
        return preview, existing_arcs

    # ── Create the node (or propose update if duplicate) ─────────────
    try:
        node = node_svc.create(data)
    except ValueError as e:
        err_str = str(e)
        if node_id and "already exists" in err_str:
            existing = node_svc.get(node_id)
            if existing:
                existing_label = resolve_node_label(node_svc, node_id)
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
                        info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
                        raise typer.Exit(0)
                else:
                    _apply_update(node_id)
                    raise typer.Exit(0)
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=err_str))
        raise typer.Exit(1) from e

    # ── Periodic FTS5 optimization ──────────────────────────────────
    global _optimize_counter
    _optimize_counter += 1
    if _optimize_counter >= _OPTIMIZE_INTERVAL:
        _optimize_counter = 0
        node_svc.optimize_fts()

    node_id_val = node["node_id"]

    # ── Check for duplicate by label (similar existing node) ────────
    if labels_dict:
        eo_label = labels_dict.get("eo") or next(iter(labels_dict.values()), None)
        if eo_label:
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

                preview_table, _ = _build_preview(
                    existing_id, old_labels, new_labels_for_update,
                    old_defns, new_defns_for_update,
                )

                if preview_table is None:
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
                    msg_same = tr_multi(
                        "Ĉu ĝi estas la sama nodo?",
                        "Is this the same node?",
                        "Est-ce le même nœud ?",
                    )
                    if confirm_action(msg_same, default=False):
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
                            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
                            raise typer.Exit(0)
                else:
                    _apply_update(existing_id, delete_new=node_id_val)
                    raise typer.Exit(0)

    # ── File attachment handling (Issue #75) ─────────────────────────
    file_triples = handle_file_attachment(
        img, filmeto, dosiero, en_loko, movi, node_id_val,
    )

    # ── Build full arcs list (arc shortcuts + file triples) ─────────
    arcs: list[dict[str, Any]] = [
        {"subject": node_id_val, "predicate": pred, "object": target_id, "object_type": "uri"}
        for target_id, pred in arc_templates
    ]
    if file_triples:
        for ft in file_triples:
            arcs.append({"subject": node_id_val, **ft})

    # ── Show preview and confirm ────────────────────────────────────
    if arcs:
        label = resolve_node_label(node_svc, node_id_val)
        if not confirm_node_with_arcs(node_svc, pred_svc, label, node_id_val, arcs, labels=labels_dict, yes=yes):
            node_svc.delete(node_id_val)
            # Clean up file if it was copied/moved
            for ft in file_triples:
                if ft["predicate"] == ":hasFilePath":
                    fp = Path(ft["object"])
                    if is_managed_file(fp):
                        delete_file(fp)
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
        ok, reason = copy_to_clipboard(node_id_val)
        if not ok:
            warning(tr_multi(
                "Ne povis kopii al poŝo: {id} — {kialo}",
                "Could not copy to clipboard: {id} — {kialo}",
                "Impossible de copier dans le presse-papier : {id} — {kialo}",
            ).format(id=node_id_val, kialo=reason))
