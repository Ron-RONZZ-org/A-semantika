"""Predikato subcommand group CLI: ls, vidi, aldoni, modifi, forigi, serci.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
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
    table.add_column("label_eo", no_wrap=True)
    table.add_column("label_en", no_wrap=True)
    table.add_column(tr_multi("Fonto", "Source", "Source"))

    for p in predicates:
        table.add_row(p["predicate_id"], p.get("label_eo", ""), p.get("label_en", ""), p.get("source", ""))

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

    info(f"ID: {pred['predicate_id']}")
    info(f"label_eo: {pred.get('label_eo', '')}")
    info(f"label_en: {pred.get('label_en', '')}")
    info(f"fonto: {pred.get('source', '')}")
    if pred.get("priskribo"):
        info(f"priskribo: {pred['priskribo']}")
    from A import info as _info
    _info(tr_multi("Kreita: {d}", "Created: {d}", "Créé : {d}").format(d=pred["kreita_je"]))
    _info(tr_multi("Modifita: {d}", "Modified: {d}", "Modifié : {d}").format(d=pred["modifita_je"]))


@predikato_app.command("aldoni")
def aldoni(
    predicate_id: str = typer.Argument(..., help=tr_multi("Predikato ID (ekz. wdt:P31)", "Predicate ID (e.g. wdt:P31)", "ID du prédicat (ex. wdt:P31)")),
    label_eo: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo en formo LANGCODE::TEKSTO", "Label as LANGCODE::TEXT", "Étiquette au format LANGCODE::TEXTE")),
    label_en: Optional[str] = typer.Option(None, "--en", help=tr_multi("Angla etikedo", "English label", "Étiquette anglaise")),
    priskribo: Optional[str] = typer.Option(None, "-p", "--priskribo", help=tr_multi("Priskribo", "Description", "Description")),
    fonto: str = typer.Option("manual", "--fonto", help=tr_multi("Fonto (wikidata|manual|owl|rdfs)", "Source (wikidata|manual|owl|rdfs)", "Source (wikidata|manual|owl|rdfs)")),
    yes: bool = typer.Option(False, "-y", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Aldoni novan predikaton."""
    pred_svc = get_predicate_service()

    existing = pred_svc.get_by_predicate_id(predicate_id)
    if existing:
        error(tr_multi("Predikato jam ekzistas: {p}", "Predicate already exists: {p}", "Prédicat existe déjà : {p}").format(p=predicate_id))
        raise typer.Exit(1)

    # Parse labels: --etikedo eo::Vorto --etikedo en::Word
    eo_label = ""
    en_label = label_en or ""
    if label_eo:
        for e in label_eo:
            if "::" in e:
                lang, _, text = e.partition("::")
                if lang == "eo" and not eo_label:
                    eo_label = text
                elif lang == "en" and not en_label:
                    en_label = text

    data = {
        "predicate_id": predicate_id,
        "label_eo": eo_label,
        "label_en": en_label,
        "priskribo": priskribo or "",
        "source": fonto,
    }

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
    label_eo: Optional[str] = typer.Option(None, "--label-eo", help=tr_multi("Esperanta etikedo", "Esperanto label", "Étiquette espéranto")),
    label_en: Optional[str] = typer.Option(None, "--label-en", help=tr_multi("Angla etikedo", "English label", "Étiquette anglaise")),
    priskribo: Optional[str] = typer.Option(None, "-p", "--priskribo", help=tr_multi("Priskribo", "Description", "Description")),
    yes: bool = typer.Option(False, "-y", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Modifi predikaton."""
    pred_svc = get_predicate_service()
    pred = pred_svc.get_by_predicate_id(predicate_id)
    if not pred:
        error(tr_multi("Predikato ne trovita: {p}", "Predicate not found: {p}", "Prédicat non trouvé : {p}").format(p=predicate_id))
        raise typer.Exit(1)

    updates = {}
    if label_eo is not None:
        updates["label_eo"] = label_eo
    if label_en is not None:
        updates["label_en"] = label_en
    if priskribo is not None:
        updates["priskribo"] = priskribo

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
        pred_svc.update(pred["uuid"], updates)
        info(tr_multi("Predikato modifita: {p}", "Predicate modified: {p}", "Prédicat modifié : {p}").format(p=predicate_id))
    except Exception as e:
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e


@predikato_app.command("forigi")
def forigi(
    predicate_id: str = typer.Argument(..., help=tr_multi("Predikato ID", "Predicate ID", "ID du prédicat")),
    yes: bool = typer.Option(False, "-y", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Forigi predikaton."""
    pred_svc = get_predicate_service()
    pred = pred_svc.get_by_predicate_id(predicate_id)
    if not pred:
        error(tr_multi("Predikato ne trovita: {p}", "Predicate not found: {p}", "Prédicat non trouvé : {p}").format(p=predicate_id))
        raise typer.Exit(1)

    if not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                f"Ĉu forigi predikaton {predicate_id}?",
                f"Delete predicate {predicate_id}?",
                f"Supprimer le prédicat {predicate_id}?",
            ),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    try:
        pred_svc.delete(pred["uuid"])
        info(tr_multi("Predikato forigita: {p}", "Predicate deleted: {p}", "Prédicat supprimé : {p}").format(p=predicate_id))
    except Exception as e:
        error(tr_multi("Foriga eraro: {e}", "Delete error: {e}", "Erreur de suppression : {e}").format(e=str(e)))
        raise typer.Exit(1) from e


@predikato_app.command("serci")
def serci(
    query: str = typer.Argument(..., help=tr_multi("Serĉa teksto", "Search text", "Texte de recherche")),
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
) -> None:
    """Serĉi predikatojn per teksto."""
    pred_svc = get_predicate_service()
    results = pred_svc.search(query, limit=limit)

    if not results:
        info(tr_multi("Neniuj predikatoj trovitaj.", "No predicates found.", "Aucun prédicat trouvé."))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("ID", "ID", "ID"), no_wrap=True)
    table.add_column("label_eo", no_wrap=True)
    table.add_column("label_en", no_wrap=True)

    for p in results:
        table.add_row(p["predicate_id"], p.get("label_eo", ""), p.get("label_en", ""))

    info(table)
