"""Predikato subcommand group CLI: ls, vidi, aldoni, modifi, forigi, serci.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning as awarning
from A.utils.interactive import confirm_action
from A_semantika.data.storage import label_from_json
from A_semantika._preview import (
    build_predicate_modify_preview,
    confirm_predicate_creation,
)
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


def _format_predicate_delete_error(err_msg: str) -> str:
    """Convert raw error strings into user-friendly messages.

    Detects FK constraint failures and translates them.
    """
    if "FOREIGN KEY constraint failed" in err_msg or "triple(s) still reference it" in err_msg:
        return tr_multi(
            "havas referencajn arkojn. Uzu --forte por perforte forigi.",
            "has referencing arcs. Use --forte to force delete.",
            "a des arcs de référence. Utilisez --forte pour forcer la suppression.",
        )
    return err_msg


def _parse_lang_value_pairs(items: list[str] | None) -> dict[str, str]:
    """Parse ``LANGCODE::TEKSTO`` list into a language→text dict.

    Accepts both ``LANGCODE::TEKSTO`` (double colon) and ``LANGCODE:TEKSTO``
    (single colon) separators.  Warns about entries with no separator.
    Strips leading/trailing whitespace from lang and text.
    """
    from A import warning as awarning

    result: dict[str, str] = {}
    if not items:
        return result
    for item in items:
        if "::" in item:
            lang, _, text = item.partition("::")
        elif ":" in item:
            lang, _, text = item.partition(":")
        else:
            awarning(tr_multi(
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
            awarning(tr_multi(
                "Malplena lingvokodo aŭ teksto en: {i}",
                "Empty language code or text in: {i}",
                "Code de langue ou texte vide dans : {i}",
            ).format(i=item))
    return result


def _get_predicate_label(pred: dict, preferred_lang: str | None = None) -> str:
    """Get the display label for a predicate dict, from etikedoj JSON.

    Args:
        pred: Predicate dict.
        preferred_lang: Optional language code to try first
            (defaults to ``eo → en → first`` fallback).
    """
    try:
        labels = json.loads(pred.get("etikedoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        labels = {}
    langs = (preferred_lang, "eo", "en") if preferred_lang else ("eo", "en")
    return label_from_json(labels, lang_fallback=langs) or pred.get("predicate_id", "")


# ── Commands ─────────────────────────────────────────────────────────────────


@predikato_app.command("ls")
def ls(
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
    lingvo: Optional[str] = typer.Option(None, "--lingvo", help=tr_multi(
        "Lingva kodo por etikedoj (ekz. eo, en, fr)",
        "Language code for labels (e.g. eo, en, fr)",
        "Code de langue pour les étiquettes (ex. eo, en, fr)",
    )),
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
        label = _get_predicate_label(p, lingvo)
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

    # Parse labels and descriptions early (needed both for create and for
    # duplicate-update before the existing predicate check).
    labels_dict = _parse_lang_value_pairs(etikedoj)
    descs_dict = _parse_lang_value_pairs(priskriboj)

    existing = pred_svc.get_by_predicate_id(predicate_id)
    if existing:
        existing_label = label_from_json(existing.get("etikedoj", {}))
        info(tr_multi("Predikato jam ekzistas: {p}", "Predicate already exists: {p}", "Prédicat existe déjà : {p}").format(p=predicate_id))
        # Only auto-prompt if not in skip-confirmation mode (-y)
        if not yes:
            msg = tr_multi(
                "Ĉu ĝi estas la sama predikato? Se jes, mi ĝisdatigos ĝin anstataŭe.",
                "Is it the same predicate? If yes, I will update it instead.",
                "Est-ce le même prédicat ? Si oui, je vais le mettre à jour à la place.",
            )
            if confirm_action(msg, default=False):
                # Build update data from user-provided labels/descriptions
                update_data: dict[str, Any] = {}
                if labels_dict:
                    update_data["etikedoj"] = labels_dict
                if descs_dict:
                    update_data["priskriboj"] = descs_dict
                if update_data:
                    pred_svc.update(predicate_id, update_data)
                info(tr_multi(
                    "Predikato ĝisdatigita: {p}",
                    "Predicate updated: {p}",
                    "Prédicat mis à jour : {p}",
                ).format(p=predicate_id))
                raise typer.Exit(0)
        # If yes=-y, just exit (don't create)
        raise typer.Exit(1)

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

    if not confirm_predicate_creation(data, yes=yes):
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
    nova_id: Optional[str] = typer.Option(None, "--nova-id", "-ni", help=tr_multi("Nova predikato-indekso (renomi)", "New predicate ID (rename)", "Nouvel ID du prédicat (renommer)")),
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

    # Parse existing values
    try:
        old_etikedoj = json.loads(pred.get("etikedoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_etikedoj = {}
    try:
        old_priskriboj = json.loads(pred.get("priskriboj", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_priskriboj = {}

    updates: dict = {}
    new_etikedoj: dict[str, str] | None = None
    new_priskriboj: dict[str, str] | None = None

    # Handle etikedoj: merge or replace
    if etikedoj is not None:
        parsed_labels = _parse_lang_value_pairs(etikedoj)
        if anstatauxigi:
            new_etikedoj = parsed_labels
        else:
            new_etikedoj = dict(old_etikedoj)
            new_etikedoj.update(parsed_labels)
        updates["etikedoj"] = new_etikedoj

    # Handle priskriboj: merge or replace
    if priskriboj is not None:
        parsed_descs = _parse_lang_value_pairs(priskriboj)
        if anstatauxigi:
            new_priskriboj = parsed_descs
        else:
            new_priskriboj = dict(old_priskriboj)
            new_priskriboj.update(parsed_descs)
        updates["priskriboj"] = new_priskriboj

    # Handle no-op for --nova-id: same as current ID
    if nova_id and nova_id == predicate_id:
        nova_id = None

    if not updates and not nova_id:
        error(tr_multi("Neniu ŝanĝo specifita.", "No changes specified.", "Aucun changement spécifié."))
        raise typer.Exit(1)

    # No-op detection: compare old vs new
    noop = (
        (new_etikedoj is None or new_etikedoj == old_etikedoj)
        and (new_priskriboj is None or new_priskriboj == old_priskriboj)
        and nova_id is None
    )
    if noop:
        info(tr_multi(
            "Neniu ŝanĝo: predikato restas neŝanĝita.",
            "No change: predicate remains unchanged.",
            "Aucun changement : le prédicat reste inchangé.",
        ))
        return

    # Show change summary and confirm
    if not yes:
        # Show rename preview even when table has no label/desc changes
        rename_preview = (
            tr_multi(
                "Predikato renomita: {old} → {new}",
                "Predicate renamed: {old} → {new}",
                "Prédicat renommé : {old} → {new}",
            ).format(old=predicate_id, new=nova_id)
            if nova_id else None
        )
        if rename_preview:
            info("")
            info(rename_preview)

        table = build_predicate_modify_preview(
            predicate_id,
            old_etikedoj, new_etikedoj,
            old_priskriboj, new_priskriboj,
        )
        if table:
            info("")
            info(table)

        if rename_preview or table:
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
        if nova_id:
            pred_svc.update_predicate_id(pred["predicate_id"], nova_id, updates)
            info(tr_multi(
                "Predikato renomita: {old} → {new}",
                "Predicate renamed: {old} → {new}",
                "Prédicat renommé : {old} → {new}",
            ).format(old=predicate_id, new=nova_id))
        else:
            pred_svc.update(pred["predicate_id"], updates)
            info(tr_multi("Predikato modifita: {p}", "Predicate modified: {p}", "Prédicat modifié : {p}").format(p=predicate_id))
    except ValueError as e:
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
    forte: bool = typer.Option(
        False, "--forte", "--force",
        help=tr_multi(
            "Perforte forigi — ankaŭ forigi arkojn kiuj referencas la predikaton",
            "Force delete — also delete triples referencing the predicate",
            "Forcer la suppression — supprimer aussi les triplets référençant le prédicat",
        ),
    ),
) -> None:
    """Forigi predikatojn."""
    pred_svc = get_predicate_service()
    from A_semantika.service import get_triple_service
    triple_svc = get_triple_service()

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

    # Phase 1b: Check for referencing triples on all resolved predicates
    ref_counts: dict[str, int] = {}
    for pred in resolved:
        pid = pred["predicate_id"]
        rc = pred_svc.count_referencing_triples(pid)
        if rc > 0:
            ref_counts[pid] = rc

    if ref_counts and not forte:
        for pid, rc in ref_counts.items():
            label = _get_predicate_label(pred_svc.get_by_predicate_id(pid))
            error(tr_multi(
                "Predikato {p} ({l}) havas {n} arko(j)n. ",
                "Predicate {p} ({l}) has {n} arc(s). ",
                "Le prédicat {p} ({l}) a {n} arc(s). ",
            ).format(p=pid, l=label, n=rc))
        error(tr_multi(
            "Uzu --forte por perforte forigi arkojn kune kun la predikato.",
            "Use --forte to force delete arcs along with the predicate.",
            "Utilisez --forte pour forcer la suppression des arcs avec le prédicat.",
        ))
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

    # Phase 3: Cascade-delete referencing triples if --forte
    if forte:
        for pid in ref_counts:
            triple_svc.remove(predicate_id=pid)

    # Phase 4: Delete each predicate
    deleted = 0
    for pred in resolved:
        try:
            pred_svc.delete(pred["predicate_id"])
            deleted += 1
        except (sqlite3.Error, ValueError) as e:
            error(tr_multi(
                "Eraro forigante {p}: {e}",
                "Error deleting {p}: {e}",
                "Erreur lors de la suppression de {p} : {e}",
                ).format(p=pred.get("predicate_id", "")[:16], e=_format_predicate_delete_error(str(e))))
            if forte:
                awarning(tr_multi(
                    "—forte estis uzata sed arkoj eble ne estis tute forigitaj.",
                    "--forte was used but arcs may not have been fully deleted.",
                    "--forte a été utilisé mais les arcs n'ont peut-être pas été entièrement supprimés.",
                ))

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
    lingvo: Optional[str] = typer.Option(None, "--lingvo", help=tr_multi(
        "Lingva kodo por etikedoj (ekz. eo, en, fr)",
        "Language code for labels (e.g. eo, en, fr)",
        "Code de langue pour les étiquettes (ex. eo, en, fr)",
    )),
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
        label = _get_predicate_label(p, lingvo)
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