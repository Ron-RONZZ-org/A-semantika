"""Predikato subcommand group CLI: ls, vidi, aldoni, modifi, forigi, serci.
"""
from __future__ import annotations

import json
from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning as awarning
from A_semantika._predicate_service import _label_from_etikedoj
from A_semantika._wikidata_helper import (
    is_wikidata_id,
    normalize_predicate_id,
    search_wikidata,
    fetch_wikidata_details,
)

from A_semantika.service import get_predicate_service

predikato_app = typer.Typer(
    name="predikato",
    help=tr_multi(
        "Administri predikatojn (semantikajn ecojn)",
        "Manage predicates (semantic properties)",
        "Gérer les prédicats (propriétés sémantiques)",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_lang_value_pairs(items: list[str] | None) -> dict[str, str]:
    """Parse ``LANGCODE::TEKSTO`` list into a language→text dict.

    Skips malformed entries (no ``::`` separator).
    """
    result: dict[str, str] = {}
    if not items:
        return result
    for item in items:
        if "::" in item:
            lang, _, text = item.partition("::")
            if lang and text:
                result[lang] = text
    return result


def _get_predicate_label(pred: dict) -> str:
    """Get the display label for a predicate dict, from etikedoj JSON."""
    try:
        labels = json.loads(pred.get("etikedoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        labels = {}
    return _label_from_etikedoj(labels) or pred.get("predicate_id", "")


# ── Commands ─────────────────────────────────────────────────────────────────


@predikato_app.command("ls")
def ls(
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
) -> None:
    """Listi ĉiujn predikatojn."""
    pred_svc = get_predicate_service()
    predicates = pred_svc.list(limit=limit)

    if not predicates:
        info(tr_multi("Neniuj predikatoj.", "No predicates.", "Aucun prédicat."))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Predikato ID", "Predicate ID", "ID prédicat"), no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)
    table.add_column(tr_multi("Fonto", "Source", "Source"))

    for p in predicates:
        label = _get_predicate_label(p)
        table.add_row(p["predicate_id"], label, p.get("source", ""))

    info(table)


@predikato_app.command("vidi")
def vidi(
    predicate_id: str = typer.Argument(..., help=tr_multi("Predikato ID", "Predicate ID", "ID du prédicat")),
) -> None:
    """Vidi detalojn de predikato."""
    pred_svc = get_predicate_service()
    pred = pred_svc.get_by_predicate_id(predicate_id)
    if not pred:
        error(tr_multi("Predikato ne trovita: {p}", "Predicate not found: {p}", "Prédicat non trouvé : {p}").format(p=predicate_id))
        raise typer.Exit(1)

    info(tr_multi("ID: {id}", "ID: {id}", "ID : {id}").format(id=pred["predicate_id"]))
    info(tr_multi("Fonto: {s}", "Source: {s}", "Source : {s}").format(s=pred.get("source", "")))

    try:
        etikedoj = json.loads(pred.get("etikedoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        etikedoj = {}
    if etikedoj:
        info(tr_multi("Etikedoj:", "Labels:", "Étiquettes :"))
        for lang, val in sorted(etikedoj.items()):
            info(f"  {lang}: {val}")

    try:
        priskriboj = json.loads(pred.get("priskriboj", "{}"))
    except (json.JSONDecodeError, TypeError):
        priskriboj = {}
    if priskriboj:
        info(tr_multi("Priskriboj:", "Descriptions:", "Descriptions :"))
        for lang, val in sorted(priskriboj.items()):
            info(f"  {lang}: {val}")

    info(tr_multi("Kreita: {d}", "Created: {d}", "Créé : {d}").format(d=pred["kreita_je"]))
    info(tr_multi("Modifita: {d}", "Modified: {d}", "Modifié : {d}").format(d=pred["modifita_je"]))


@predikato_app.command("aldoni")
def aldoni(
    predicate_id: str = typer.Argument(..., help=tr_multi("Predikato ID (ekz. wdt:P31)", "Predicate ID (e.g. wdt:P31)", "ID du prédicat (ex. wdt:P31)")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANGCODE::TEKSTO (ripetebla)", "Label as LANGCODE::TEXT (repeatable)", "Étiquette au format LANGCODE::TEXTE (répétable)")),
    priskriboj: Optional[list[str]] = typer.Option(None, "-p", "--priskribo", help=tr_multi("Priskribo en formo LANGCODE::TEKSTO (ripetebla)", "Description as LANGCODE::TEXT (repeatable)", "Description au format LANGCODE::TEXTE (répétable)")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Aldoni novan predikaton.

    Uzu -e por etikedoj kaj -p por priskriboj, en formo LANGCODE::TEKSTO.
    Ekz: predikato aldoni wdt:P31 -e eo::tipo -e en::instance of -p eo::Priskribo
    """
    pred_svc = get_predicate_service()

    # Auto-detect and normalize Wikidata IDs
    is_wd = is_wikidata_id(predicate_id)
    if is_wd:
        predicate_id = normalize_predicate_id(predicate_id)

    existing = pred_svc.get_by_predicate_id(predicate_id)
    if existing:
        error(tr_multi("Predikato jam ekzistas: {p}", "Predicate already exists: {p}", "Prédicat existe déjà : {p}").format(p=predicate_id))
        raise typer.Exit(1)

    # Parse labels and descriptions from LANGCODE::TEKSTO format
    labels_dict = _parse_lang_value_pairs(etikedoj)
    descs_dict = _parse_lang_value_pairs(priskriboj)

    # Auto-fetch Wikidata details for Wikidata property IDs
    wd_details: dict | None = None
    if is_wd:
        wd_details = fetch_wikidata_details(predicate_id)

    # Build data: auto-fetched values as base, user labels merge/override
    data: dict = {}
    if wd_details:
        data = dict(wd_details)
        # Merge user-provided labels with auto-fetched (user overrides per-lang)
        if labels_dict:
            merged_labels = dict(data.get("etikedoj", {}))
            merged_labels.update(labels_dict)
            data["etikedoj"] = merged_labels
        if descs_dict:
            merged_descs = dict(data.get("priskriboj", {}))
            merged_descs.update(descs_dict)
            data["priskriboj"] = merged_descs
        # Force source=wikidata for Wikidata IDs
        data["source"] = "wikidata"
    else:
        effective_source = "wikidata" if is_wd else "manual"
        data = {
            "predicate_id": predicate_id,
            "etikedoj": labels_dict,
            "priskriboj": descs_dict,
            "source": effective_source,
        }
        if is_wd:
            awarning(tr_multi(
                "Ne povis aŭtomate preni etikedojn de Vikidatumoj. Kreante mane.",
                "Could not auto-fetch labels from Wikidata. Creating manually.",
                "Impossible de récupérer les étiquettes depuis Wikidata. Création manuelle.",
            ))

    if not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                f"Ĉu krei predikaton {predicate_id}?",
                f"Create predicate {predicate_id}?",
                f"Créer le prédicat {predicate_id}?",
            ),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    try:
        pred_svc.create(data)
        info(tr_multi("Predikato kreita: {p}", "Predicate created: {p}", "Prédicat créé : {p}").format(p=predicate_id))
    except ValueError as e:
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e


@predikato_app.command("modifi")
def modifi(
    predicate_id: str = typer.Argument(..., help=tr_multi("Predikato ID", "Predicate ID", "ID du prédicat")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANGCODE::TEKSTO (ripetebla, kunfandema)", "Label as LANGCODE::TEXT (repeatable, merge)", "Étiquette au format LANGCODE::TEXTE (répétable, fusion)")),
    priskriboj: Optional[list[str]] = typer.Option(None, "-p", "--priskribo", help=tr_multi("Priskribo en formo LANGCODE::TEKSTO (ripetebla, kunfandema)", "Description as LANGCODE::TEXT (repeatable, merge)", "Description au format LANGCODE::TEXTE (répétable, fusion)")),
    anstatauxigi: bool = typer.Option(False, "-r", "--anstatauxigi", "--anstataŭigi", help=tr_multi("Anstataŭigi anstataŭ kunfandi etikedojn/priskribojn", "Replace instead of merging labels/descriptions", "Remplacer au lieu de fusionner les étiquettes/descriptions")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Modifi predikaton.

    Defaŭlte -e kaj -p KUNFANDAS novajn valorojn kun ekzistantaj (aldonas/ĝisdatigas).
    Uzu -r por ANSTATAŬIGI (forigi ĉiujn ekzistantajn kaj uzi nur la specifitajn).

    Ekzemploj:
      predikato modifi wdt:P31 -e fr::type        # aldoni francan etikedon
      predikato modifi wdt:P31 -e fr::type -r      # anstataŭigi per nur franca
    """
    pred_svc = get_predicate_service()
    pred = pred_svc.get_by_predicate_id(predicate_id)
    if not pred:
        error(tr_multi("Predikato ne trovita: {p}", "Predicate not found: {p}", "Prédicat non trouvé : {p}").format(p=predicate_id))
        raise typer.Exit(1)

    updates: dict = {}

    # Handle etikedoj: merge or replace
    if etikedoj is not None:
        new_labels = _parse_lang_value_pairs(etikedoj)
        if anstatauxigi:
            updates["etikedoj"] = new_labels
        else:
            # Merge: load existing, update with new values
            try:
                existing_labels = json.loads(pred.get("etikedoj", "{}"))
            except (json.JSONDecodeError, TypeError):
                existing_labels = {}
            existing_labels.update(new_labels)
            updates["etikedoj"] = existing_labels

    # Handle priskriboj: merge or replace
    if priskriboj is not None:
        new_descs = _parse_lang_value_pairs(priskriboj)
        if anstatauxigi:
            updates["priskriboj"] = new_descs
        else:
            try:
                existing_descs = json.loads(pred.get("priskriboj", "{}"))
            except (json.JSONDecodeError, TypeError):
                existing_descs = {}
            existing_descs.update(new_descs)
            updates["priskriboj"] = existing_descs

    if not updates:
        error(tr_multi("Neniu ŝanĝo specifita.", "No changes specified.", "Aucun changement spécifié."))
        raise typer.Exit(1)

    if not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                f"Ĉu modifi predikaton {predicate_id}?",
                f"Modify predicate {predicate_id}?",
                f"Modifier le prédicat {predicate_id}?",
            ),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    try:
        pred_svc.update(pred["predicate_id"], updates)
        info(tr_multi("Predikato modifita: {p}", "Predicate modified: {p}", "Prédicat modifié : {p}").format(p=predicate_id))
    except Exception as e:
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e


@predikato_app.command("forigi")
def forigi(
    predicate_ids: list[str] = typer.Argument(
        ...,
        help=tr_multi(
            "Predikato ID-oj (pluraj)",
            "Predicate IDs (multiple)",
            "IDs des prédicats (plusieurs)",
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
    """Forigi predikatojn."""
    pred_svc = get_predicate_service()

    # Phase 1: Resolve all identifiers
    resolved: list[dict] = []
    errors: list[tuple[str, str]] = []

    for pid in predicate_ids:
        pred = pred_svc.get_by_predicate_id(pid)
        if pred:
            resolved.append(pred)
        else:
            errors.append((pid, tr_multi("ne trovita", "not found", "non trouvé")))

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
        table.add_column(tr_multi("Predikato ID", "Predicate ID", "ID prédicat"), no_wrap=True)
        table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)
        for pred in resolved:
            label = _get_predicate_label(pred)
            table.add_row(pred["predicate_id"], label)
        info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu forigi {n} predikatojn?", "Delete {n} predicates?", "Supprimer {n} prédicats?",
            ).format(n=len(resolved)),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Phase 3: Delete each
    deleted = 0
    for pred in resolved:
        try:
            pred_svc.delete(pred["predicate_id"])
            deleted += 1
        except Exception as e:
            error(tr_multi(
                "Eraro forigante {p}: {e}",
                "Error deleting {p}: {e}",
                "Erreur lors de la suppression de {p} : {e}",
                ).format(p=pred.get("predicate_id", pred["predicate_id"][:8]), e=str(e)))

    info(tr_multi(
        "Forigis {d} el {t} predikatojn.",
        "Deleted {d} of {t} predicates.",
        "Supprimé {d} sur {t} prédicats.",
    ).format(d=deleted, t=len(resolved)))


@predikato_app.command("serci")
def serci(
    query: str = typer.Argument(..., help=tr_multi("Serĉa teksto", "Search text", "Texte de recherche")),
    wikidata: bool = typer.Option(False, "--wikidata", "-w", help=tr_multi("Ankaŭ serĉi en Vikidatumoj", "Also search Wikidata", "Chercher aussi dans Wikidata")),
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
) -> None:
    """Serĉi predikatojn per teksto."""
    pred_svc = get_predicate_service()
    results = pred_svc.search(query, limit=limit)

    # Merge Wikidata results if requested
    wikidata_results: list[dict] = []
    if wikidata:
        raw_wd = search_wikidata(query)
        # Deduplicate by predicate_id
        local_ids = {r["predicate_id"] for r in results}
        for wd in raw_wd:
            if wd["predicate_id"] not in local_ids:
                wikidata_results.append(wd)
                if len(wikidata_results) >= limit:
                    break

    # Show hint when local search is empty
    if not results:
        if not wikidata:
            info(tr_multi(
                "Neniuj lokaj rezultoj. Provu: predikato serci -w <query>",
                "No local results. Try: predikato serci -w <query>",
                "Aucun résultat local. Essayez : predikato serci -w <query>",
            ))
            return
        if not wikidata_results:
            info(tr_multi("Neniuj rezultoj.", "No results.", "Aucun résultat."))
            return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("ID", "ID", "ID"), no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=True)

    has_wikidata = bool(wikidata_results)
    if has_wikidata:
        table.add_column(tr_multi("Fonto", "Source", "Source"))

    for p in results:
        label = _get_predicate_label(p)
        row: list[str] = [p["predicate_id"], label]
        if has_wikidata:
            row.append(tr_multi("loka", "local", "local"))
        table.add_row(*row)

    for wd in wikidata_results:
        table.add_row(
            wd["predicate_id"],
            wd.get("label", ""),
            tr_multi("vikidatumoj", "Wikidata", "Wikidata"),
        )

    info(table)