"""Query/read-only root triple commands: serci, vidi, eksporti.

Extracted from _cli_triples.py to keep each file under 500 lines.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A.utils.date import date_range
from A_semantika._cli_helpers import (
    _prompt_select_ambiguous_node,
    resolve_deprecated,
)
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika._preview_triple import format_tipo
from A_semantika._triple_search import search_triples_any_field, search_triples_by_labels
from A_semantika.service import get_node_service, get_predicate_service, get_triple_service, get_provo_service


# ── Commands ──────────────────────────────────────────────────────────


def serci(
    search_term: Optional[str] = typer.Argument(
        None,
        metavar="[SEARCH_TERM]",
        help=tr_multi(
            "Serĉi tra ĉiuj kampoj (subjekto, predikato, objekto)"
            " — unue provas kongruigi ID, poste etikedojn",
            "Search across all fields (subject, predicate, object)"
            " — first tries ID match, then labels",
            "Rechercher dans tous les champs (sujet, prédicat, objet)"
            " — essaie d'abord l'ID, puis les étiquettes",
        ),
    ),
    subjekto: Optional[str] = typer.Option(
        None, "--subjekto", "-s",
        help=tr_multi(
            "Subjekto UUID-prefikso aŭ etikedo",
            "Subject UUID prefix or label",
            "Préfixe UUID ou étiquette du sujet",
        ),
    ),
    subject: Optional[str] = typer.Option(
        None, "--subject", hidden=True,
        help=tr_multi(
            "Subjekto UUID-prefikso aŭ etikedo",
            "Subject UUID prefix or label",
            "Préfixe UUID ou étiquette du sujet",
        ),
    ),
    predikato: Optional[str] = typer.Option(
        None, "--predikato", "-p",
        help=tr_multi(
            "Predikato ID aŭ parta nomo",
            "Predicate ID or partial name",
            "ID du prédicat ou nom partiel",
        ),
    ),
    predicate: Optional[str] = typer.Option(
        None, "--predicate", hidden=True,
        help=tr_multi(
            "Predikato ID aŭ parta nomo",
            "Predicate ID or partial name",
            "ID du prédicat ou nom partiel",
        ),
    ),
    objekto: Optional[str] = typer.Option(
        None, "--objekto", "-o",
        help=tr_multi(
            "Objekto UUID-prefikso, etikedo aŭ valoro",
            "Object UUID prefix, label or value",
            "Préfixe UUID objet, étiquette ou valeur",
        ),
    ),
    object: Optional[str] = typer.Option(  # noqa: A002
        None, "--object", hidden=True,
        help=tr_multi(
            "Objekto UUID-prefikso, etikedo aŭ valoro",
            "Object UUID prefix, label or value",
            "Préfixe UUID objet, étiquette ou valeur",
        ),
    ),
    limit: int = typer.Option(
        50, "--limit", "-l",
        help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max"),
    ),
    dato_de: Optional[str] = typer.Option(
        None, "--dato-de", "--from",
        help=tr_multi(
            "Komenca dato (YYYYMMDD, MMDD, aŭ DD)",
            "Start date (YYYYMMDD, MMDD, or DD)",
            "Date de début (AAAAMMJJ, MMJJ ou JJ)",
        ),
    ),
    dato_gis: Optional[str] = typer.Option(
        None, "--dato-gis", "--until",
        help=tr_multi(
            "Fina dato (YYYYMMDD, MMDD, aŭ DD)",
            "End date (YYYYMMDD, MMDD, or DD)",
            "Date de fin (AAAAMMJJ, MMJJ ou JJ)",
        ),
    ),
) -> None:
    """Serĉi arkojn laŭ subjekto, predikato aŭ objekto."""
    # Resolve deprecated aliases
    subject = resolve_deprecated(subjekto, subject, "subject", "subjekto")
    predicate = resolve_deprecated(predikato, predicate, "predicate", "predikato")
    object = resolve_deprecated(objekto, object, "object", "objekto")  # noqa: A002

    # Convert partial date tokens to ISO 8601 strings
    try:
        iso_de, iso_gis = date_range(dato_de, dato_gis)
    except ValueError as e:
        error(tr_multi(
            "Nevalida dato: {e}",
            "Invalid date: {e}",
            "Date invalide : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e

    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()
    provo_svc = get_provo_service()

    # If a positional search_term is given without explicit flags,
    # search across all three fields (subject, predicate, object) with
    # OR logic — any field matching returns the triple.
    # Explicit flags take priority over search_term.
    if search_term and not (subject or predicate or object):
        results = search_triples_any_field(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            search_term=search_term,
            limit=limit,
            dato_de=iso_de,
            dato_gis=iso_gis,
        )
    elif subject or predicate or object:
        # Use the existing AND-across-fields search when explicit flags are given
        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            subject=subject,
            predicate=predicate,
            object=object,
            limit=limit,
            dato_de=iso_de,
            dato_gis=iso_gis,
        )
    else:
        # No filters: show all triples (with optional date filtering)
        where = "1=1"
        params: list = []
        if iso_de:
            where += " AND kreita_je >= ?"
            params.append(iso_de)
        if iso_gis:
            where += " AND kreita_je <= ?"
            params.append(iso_gis)
        params.append(limit)
        results = triple_svc.db.execute(
            f"SELECT * FROM triples WHERE {where} ORDER BY subject_uuid LIMIT ?",
            params,
        )

    if not results:
        info(tr_multi("Neniuj arkoj trovitaj.", "No arcs found.", "Aucun arc trouvé."))
        return

    # ── Annotate results with proof info ──────────────────────────
    # Collect unique arc keys and batch-query proofs for all of them.
    arcs_for_proofs = [
        (r["subject_uuid"], r["predicate_id"], r["object_value"])
        for r in results
    ]
    proof_map = provo_svc.get_proofs_for_arcs_batch(arcs_for_proofs)
    for r in results:
        key = (r["subject_uuid"], r["predicate_id"], r["object_value"])
        stmt_nodes = proof_map.get(key, [])
        if stmt_nodes:
            r["proof_stmt_ids"] = stmt_nodes
        else:
            r["proof_stmt_ids"] = []

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    # Object column allows wrapping: literal values can be long text
    # (paragraphs, sentences).  no_wrap=True would truncate them or
    # force truncation of other columns to fit the terminal width.
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=False)
    table.add_column(tr_multi("Tipo", "Type", "Type"), no_wrap=True)

    # Collect all UUIDs for context-aware truncation
    all_subject_uuids = [r["subject_uuid"] for r in results]
    all_object_uuids = [r["object_value"] for r in results if r["object_type"] == "uri"]
    for r in results:
        s_label = resolve_node_label(node_svc, r["subject_uuid"])
        p_label = resolve_predicate_label(pred_svc, r["predicate_id"])
        # Append proof indicators to the predicate label
        proof_stmt_ids = r.get("proof_stmt_ids", [])
        if proof_stmt_ids:
            if len(proof_stmt_ids) == 1:
                p_label += f" (:pruvo {truncate_uuid(proof_stmt_ids[0])})"
            elif len(proof_stmt_ids) <= 3:
                parts = [truncate_uuid(n) for n in proof_stmt_ids]
                p_label += f" (:pruvoj {', '.join(parts)})"
            else:
                p_label += f" (:pruvoj x{len(proof_stmt_ids)})"
        if r["object_type"] == "uri":
            o_label = resolve_node_label(node_svc, r["object_value"])
            o_display = f"{o_label} ({truncate_uuid(r['object_value'], all_object_uuids)})"
        else:
            o_label = r["object_value"]
            o_display = o_label

        # Resolve unit node_id to display label
        unit_display = None
        if r.get("object_unit") and r.get("object_type") == "literal" and r.get("object_datatype") in ("xsd:integer", "xsd:decimal"):
            try:
                unit_node = node_svc.resolve_node_id_prefix(r["object_unit"])
                if unit_node:
                    unit_display = resolve_node_label(node_svc, unit_node["node_id"])
            except AmbiguousUUIDError:
                pass
            if not unit_display:
                unit_display = truncate_uuid(r["object_unit"])

        table.add_row(
            f"{s_label} ({truncate_uuid(r['subject_uuid'], all_subject_uuids)})",
            p_label,
            o_display,
            format_tipo(
                r.get("object_type", "uri"),
                r.get("object_datatype"),
                r.get("object_lang"),
                unit_display,
            ),
        )

    info(table)
    info(tr_multi(
        "{n} arkoj trovita(j).",
        "{n} arc(s) found.",
        "{n} arc(s) trouvé(s).",
    ).format(n=len(results)))


def vidi(
    subject_uuid: str = typer.Argument(
        ...,
        metavar="SUBJEKTO_UUID",
        help=tr_multi(
            "Subjekto UUID-prefikso",
            "Subject UUID prefix",
            "Préfixe UUID du sujet",
        ),
    ),
) -> None:
    """Vidi ĉiujn arkojn por nodo (subjekto)."""
    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    try:
        subj_node = node_svc.resolve_node_id_prefix(subject_uuid)
    except AmbiguousUUIDError as e:
        if e.matches:
            subj_node = _prompt_select_ambiguous_node(node_svc, e.matches)
            if subj_node is None:
                raise typer.Exit(1)
        else:
            error(tr_multi(
                "Ambigua subjekto-prefikso: {e}",
                "Ambiguous subject prefix: {e}",
                "Préfixe sujet ambigu : {e}",
            ).format(e=str(e)))
            raise typer.Exit(1) from e
    if not subj_node:
        # Fallback: substring match
        try:
            subj_node = node_svc.resolve_node_id_substring(subject_uuid)
        except AmbiguousUUIDError as e:
            if e.matches:
                subj_node = _prompt_select_ambiguous_node(node_svc, e.matches)
                if subj_node is None:
                    raise typer.Exit(1)
            else:
                error(tr_multi(
                    "Ambigua subjekto: {e}",
                    "Ambiguous subject: {e}",
                    "Sujet ambigu : {e}",
                ).format(e=str(e)))
                raise typer.Exit(1) from e
    if not subj_node:
        error(tr_multi(
            "Nodo ne trovita: {s}",
            "Node not found: {s}",
            "Nœud non trouvé : {s}",
        ).format(s=subject_uuid))
        raise typer.Exit(1)

    subj_label = resolve_node_label(node_svc, subj_node["node_id"])
    from A import info as _info

    _info(tr_multi(
        "Nodo: {label} ({uuid})",
        "Node: {label} ({uuid})",
        "Nœud : {label} ({uuid})",
    ).format(label=subj_label, uuid=truncate_uuid(subj_node["node_id"])))

    results = triple_svc.get_subject_objects(subj_node["node_id"])
    if not results:
        info(tr_multi(
            "Neniuj arkoj por tiu nodo.",
            "No arcs for this node.",
            "Aucun arc pour ce nœud.",
        ))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=False)
    table.add_column(tr_multi("Tipo", "Type", "Type"), no_wrap=True)

    for r in results:
        p_label = resolve_predicate_label(pred_svc, r["predicate_id"])
        if r["object_type"] == "uri":
            o_label = resolve_node_label(node_svc, r["object_value"])
        else:
            o_label = r["object_value"]
        # Resolve unit node_id to display label for vidi output
        unit_display = None
        if r.get("object_unit") and r.get("object_type") == "literal" and r.get("object_datatype") in ("xsd:integer", "xsd:decimal"):
            try:
                unit_node = node_svc.resolve_node_id_prefix(r["object_unit"])
                if unit_node:
                    unit_display = resolve_node_label(node_svc, unit_node["node_id"])
            except AmbiguousUUIDError:
                pass
            if not unit_display:
                unit_display = truncate_uuid(r["object_unit"])

        table.add_row(
            p_label,
            o_label,
            format_tipo(
                r.get("object_type", "uri"),
                r.get("object_datatype"),
                r.get("object_lang"),
                unit_display,
            ),
        )

    info(table)


def eksporti(
    output: Optional[str] = typer.Option(
        None, "--output", "-o",
        help=tr_multi(
            "Eliga dosiero (defaŭlte: stdout)",
            "Output file (default: stdout)",
            "Fichier de sortie (défaut: stdout)",
        ),
    ),
    base_uri: str = typer.Option(
        "https://example.org/", "--base-uri", "-b",
        help=tr_multi(
            "Baza URI por Turtle",
            "Base URI for Turtle",
            "URI de base pour Turtle",
        ),
    ),
) -> None:
    """Eksporti ĉiujn arkojn al Turtle (.ttl) formato."""
    triple_svc = get_triple_service()

    try:
        ttl = triple_svc.export_turtle(base_uri=base_uri)
    except (sqlite3.Error, ValueError) as e:
        error(tr_multi(
            "Eksporta eraro: {e}",
            "Export error: {e}",
            "Erreur d'export : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e

    if output:
        output_path = Path(output).resolve()
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(ttl)
            info(tr_multi(
                "Eksportita al {path}",
                "Exported to {path}",
                "Exporté vers {path}",
            ).format(path=str(output_path)))
        except OSError as e:
            error(tr_multi(
                "Ne povis skribi al {path}: {e}",
                "Could not write to {path}: {e}",
                "Impossible d'écrire dans {path} : {e}",
            ).format(path=str(output_path), e=str(e)))
            raise typer.Exit(1) from e
    else:
        sys.stdout.write(ttl)
