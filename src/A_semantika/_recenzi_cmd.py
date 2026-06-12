"""Recenzi (interactive review) subcommand group: rigardi, multobla, historio, vidi, forigi.

Allows users to review triples interactively — either one-by-one (rigardi)
or as multiple-choice quizzes (multobla).
"""
from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A.utils.date import date_range
from A.utils.interactive import confirm_action
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika._reczeni_helpers import (
    add_result,
    build_question_data,
    create_session,
    delete_session,
    finish_session,
    get_results,
    get_session,
    get_triples_for_review,
    list_sessions,
    update_session_score,
)
from A_semantika.service import get_node_service, get_predicate_service, get_triple_service

recenzi_app = typer.Typer(
    name="recenzi",
    help=tr_multi(
        "Interaga revizia reĝimo por arkoj",
        "Interactive arc review mode",
        "Mode de révision interactif des arcs",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


def _parse_date_range(
    dato_de: str | None,
    dato_gis: str | None,
) -> tuple[str | None, str | None]:
    """Parse and validate date range, exiting on failure."""
    try:
        return date_range(dato_de, dato_gis)
    except ValueError as e:
        error(tr_multi(
            "Nevalida dato: {e}",
            "Invalid date: {e}",
            "Date invalide : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e


@recenzi_app.command("rigardi")
def rigardi(
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
    limit: int = typer.Option(
        10, "--limit", "-l",
        help=tr_multi(
            "Nombro da arkoj por revizii",
            "Number of arcs to review",
            "Nombre d'arcs à réviser",
        ),
    ),
) -> None:
    """Paŝi tra arkoj unu post la alia, konfirmante ĉiun."""
    iso_de, iso_gis = _parse_date_range(dato_de, dato_gis)
    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    triples = get_triples_for_review(triple_svc, iso_de, iso_gis, limit=limit)
    if not triples:
        info(tr_multi(
            "Neniuj arkoj trovitaj en tiu dato-intervalo.",
            "No arcs found in that date range.",
            "Aucun arc trouvé dans cet intervalle de dates.",
        ))
        return

    sesio = create_session("rigardi", iso_de, iso_gis)
    totalo = len(triples)
    korekta = 0

    for i, triple in enumerate(triples):
        qdata = build_question_data(triple, node_svc, pred_svc, triple_svc, mode="rigardi")
        _show_rigardi_prompt(qdata, i + 1, totalo)
        user_val = sys.stdin.readline().strip().lower()
        # Default: correct (empty or affirmative)
        is_correct = not user_val or user_val in ("j", "jes", "y", "yes", "oui")

        add_result(
            sesio["uuid"],
            triple["subject_uuid"],
            triple["predicate_id"],
            triple["object_value"],
            triple["object_type"],
            korekta=is_correct,
            respondo="jes" if is_correct else "ne",
            pozicio=i + 1,
        )
        if is_correct:
            korekta += 1

    update_session_score(sesio["uuid"], korekta, totalo)
    finish_session(sesio["uuid"])
    _show_score(korekta, totalo)


@recenzi_app.command("multobla")
def multobla(
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
    limit: int = typer.Option(
        10, "--limit", "-l",
        help=tr_multi(
            "Nombro da demandoj",
            "Number of questions",
            "Nombre de questions",
        ),
    ),
) -> None:
    """Plur-elekta kvizo: montri subjekton+predikaton, elekti ĝustan objekton."""
    iso_de, iso_gis = _parse_date_range(dato_de, dato_gis)
    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    triples = get_triples_for_review(triple_svc, iso_de, iso_gis, limit=limit)
    if not triples:
        info(tr_multi(
            "Neniuj arkoj trovitaj en tiu dato-intervalo.",
            "No arcs found in that date range.",
            "Aucun arc trouvé dans cet intervalle de dates.",
        ))
        return

    sesio = create_session("multobla", iso_de, iso_gis)
    totalo = len(triples)
    korekta = 0

    for i, triple in enumerate(triples):
        qdata = build_question_data(triple, node_svc, pred_svc, triple_svc, mode="multobla")
        options = qdata.get("options", [triple["object_value"]])
        _show_multobla_prompt(qdata, i + 1, totalo, options)

        user_input = sys.stdin.readline().strip()
        if not user_input or not user_input.isdigit():
            idx = -1
        else:
            idx = int(user_input) - 1

        is_correct = 0 <= idx < len(options) and options[idx] == triple["object_value"]
        respondo = options[idx] if 0 <= idx < len(options) else (user_input or "")

        add_result(
            sesio["uuid"],
            triple["subject_uuid"],
            triple["predicate_id"],
            triple["object_value"],
            triple["object_type"],
            korekta=is_correct,
            respondo=respondo,
            pozicio=i + 1,
        )
        if is_correct:
            korekta += 1
        else:
            _show_correct_answer(qdata)

    update_session_score(sesio["uuid"], korekta, totalo)
    finish_session(sesio["uuid"])
    _show_score(korekta, totalo)


@recenzi_app.command("historio")
def historio(
    limit: int = typer.Option(
        20, "--limit", "-l",
        help=tr_multi("Maksimume sesioj", "Max sessions", "Sessions max"),
    ),
) -> None:
    """Listi pasintajn reviziajn sesiojn."""
    sessions = list_sessions(limit=limit)
    if not sessions:
        info(tr_multi(
            "Neniuj pasintaj sesioj.",
            "No past sessions.",
            "Aucune session passée.",
        ))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("UUID", "UUID", "UUID"), no_wrap=True)
    table.add_column(tr_multi("Reĝimo", "Mode", "Mode"), no_wrap=True)
    table.add_column(tr_multi("Poentaro", "Score", "Score"), no_wrap=True)
    table.add_column(tr_multi("Stato", "Status", "Statut"), no_wrap=True)
    table.add_column(tr_multi("Kreita", "Created", "Créé"), no_wrap=True)

    for s in sessions:
        modo_label = (
            tr_multi("Vidado", "View", "Vision")
            if s["modo"] == "rigardi" else
            tr_multi("Multobla", "Multiple", "Multiple")
        )
        score = f"{s['korekta']}/{s['totalo']}" if s["totalo"] else "—"
        status = (
            tr_multi("Finita", "Finished", "Terminé")
            if s["finita"] else
            tr_multi("Daŭranta", "Ongoing", "En cours")
        )
        table.add_row(
            s["uuid"][:8],
            modo_label,
            score,
            status,
            s["kreita_je"][:19],
        )

    info(table)


@recenzi_app.command("vidi")
def vidi(
    sesio_uuid: str = typer.Argument(
        ...,
        metavar="SESIO_UUID",
        help=tr_multi(
            "Sesio UUID-prefikso",
            "Session UUID prefix",
            "Préfixe UUID de session",
        ),
    ),
) -> None:
    """Vidi detalojn de revizia sesio."""
    node_svc = get_node_service()
    pred_svc = get_predicate_service()

    # Resolve session UUID prefix
    db_sessions = list_sessions(limit=100)
    matched = [s for s in db_sessions if s["uuid"].startswith(sesio_uuid)]
    if not matched:
        error(tr_multi(
            "Sesio ne trovita: {u}",
            "Session not found: {u}",
            "Session non trouvée : {u}",
        ).format(u=sesio_uuid))
        raise typer.Exit(1)
    if len(matched) > 1:
        error(tr_multi(
            "Ambigua sesio-prefikso: {u}",
            "Ambiguous session prefix: {u}",
            "Préfixe de session ambigu : {u}",
        ).format(u=sesio_uuid))
        raise typer.Exit(1)

    sesio = matched[0]
    results = get_results(sesio["uuid"])

    modo_label = (
        tr_multi("Vidado", "View", "Vision")
        if sesio["modo"] == "rigardi" else
        tr_multi("Multobla", "Multiple", "Multiple")
    )
    info(tr_multi(
        "Sesio: {m} — Poentaro: {k}/{t}",
        "Session: {m} — Score: {k}/{t}",
        "Session : {m} — Score : {k}/{t}",
    ).format(m=modo_label, k=sesio["korekta"], t=sesio["totalo"]))

    if not results:
        info(tr_multi(
            "Neniuj rezultoj en tiu sesio.",
            "No results in that session.",
            "Aucun résultat dans cette session.",
        ))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("#", no_wrap=True)
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=False)
    table.add_column(tr_multi("Ĝusta?", "Correct?", "Correct ?"), no_wrap=True)
    table.add_column(tr_multi("Respondo", "Answer", "Réponse"), no_wrap=False)

    for r in results:
        s_label = resolve_node_label(node_svc, r["subject_uuid"])
        p_label = resolve_predicate_label(pred_svc, r["predicate_id"])
        if r["object_type"] == "uri":
            o_label = resolve_node_label(node_svc, r["object_value"])
        else:
            o_label = r["object_value"]
        correct_mark = "✓" if r["korekta"] else "✗"
        table.add_row(
            str(r["pozicio"]),
            s_label,
            p_label,
            o_label,
            correct_mark,
            r["respondo"] or "—",
        )

    info(table)


@recenzi_app.command("forigi")
def forigi(
    sesio_uuid: str = typer.Argument(
        ...,
        metavar="SESIO_UUID",
        help=tr_multi(
            "Sesio UUID",
            "Session UUID",
            "UUID de session",
        ),
    ),
    yes: bool = typer.Option(
        False, "-y", "--jes", "--yes",
        help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation"),
    ),
) -> None:
    """Forigi revizian sesion."""
    db_sessions = list_sessions(limit=100)
    matched = [s for s in db_sessions if s["uuid"].startswith(sesio_uuid)]
    if not matched:
        error(tr_multi(
            "Sesio ne trovita: {u}",
            "Session not found: {u}",
            "Session non trouvée : {u}",
        ).format(u=sesio_uuid))
        raise typer.Exit(1)
    if len(matched) > 1:
        error(tr_multi(
            "Ambigua sesio-prefikso: {u}",
            "Ambiguous session prefix: {u}",
            "Préfixe de session ambigu : {u}",
        ).format(u=sesio_uuid))
        raise typer.Exit(1)

    if not yes:
        if not confirm_action(
            tr_multi(
                "Ĉu forigi sesion {u}?",
                "Delete session {u}?",
                "Supprimer la session {u} ?",
            ).format(u=matched[0]["uuid"][:8]),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    deleted = delete_session(matched[0]["uuid"])
    if deleted:
        info(tr_multi(
            "Sesio forigita.",
            "Session deleted.",
            "Session supprimée.",
        ))
    else:
        error(tr_multi(
            "Eraro forigante sesion.",
            "Error deleting session.",
            "Erreur lors de la suppression de la session.",
        ))
        raise typer.Exit(1)


# ── Display helpers ──────────────────────────────────────────────────────────


def _show_rigardi_prompt(qdata: dict, current: int, total: int) -> None:
    """Show a rigardi (view) prompt for one triple."""
    info(tr_multi(
        "\n[{c}/{t}] Subjekto: {s} — Predikato: {p}",
        "\n[{c}/{t}] Subject: {s} — Predicate: {p}",
        "\n[{c}/{t}] Sujet : {s} — Prédicat : {p}",
    ).format(c=current, t=total, s=qdata["subject_label"], p=qdata["predicate_label"]))
    info(tr_multi(
        "Objekto: {o}  [{tipo}]",
        "Object: {o}  [{tipo}]",
        "Objet : {o}  [{tipo}]",
    ).format(o=qdata["object_display"], tipo=qdata["object_type"]))
    print(tr_multi(
        "Ĉu ĝuste? [J/n] ", "Correct? [Y/n] ", "Correct ? [O/n] ",
    ), end="", flush=True)


def _show_multobla_prompt(qdata: dict, current: int, total: int, options: list[str]) -> None:
    """Show a multobla (multiple-choice) prompt."""
    info(tr_multi(
        "\n[{c}/{t}] Subjekto: {s} — Predikato: {p}",
        "\n[{c}/{t}] Subject: {s} — Predicate: {p}",
        "\n[{c}/{t}] Sujet : {s} — Prédicat : {p}",
    ).format(c=current, t=total, s=qdata["subject_label"], p=qdata["predicate_label"]))
    info(tr_multi(
        "Elektu la ĝustan objekton:",
        "Choose the correct object:",
        "Choisissez le bon objet :",
    ))
    for idx, opt in enumerate(options):
        print(f"  {idx + 1}. {opt}")
    print(tr_multi(
        "Via elekto (numero): ",
        "Your choice (number): ",
        "Votre choix (numéro) : ",
    ), end="", flush=True)


def _show_correct_answer(qdata: dict) -> None:
    """Show the correct answer after a wrong response."""
    info(tr_multi(
        "Ĝusta: {o}",
        "Correct: {o}",
        "Correct : {o}",
    ).format(o=qdata["object_display"]))


def _show_score(korekta: int, totalo: int) -> None:
    """Show the final score."""
    pct = (korekta / totalo * 100) if totalo else 0
    info(tr_multi(
        "Sesio finita. Poentaro: {k}/{t} ({p:.0f}%)",
        "Session finished. Score: {k}/{t} ({p:.0f}%)",
        "Session terminée. Score : {k}/{t} ({p:.0f}%)",
    ).format(k=korekta, t=totalo, p=pct))
