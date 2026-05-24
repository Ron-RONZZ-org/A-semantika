"""Modifi command for root triple operations.

Extracted from _cli_triples.py to keep each file under 500 lines.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika._cli_helpers import pick_triple, resolve_deprecated
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_triple_service,
)


def modifi(
    subject: str = typer.Argument(
        ...,
        metavar="SUBJEKTO",
        help=tr_multi(
            "Nuna subjekto UUID-prefikso aŭ etikedo",
            "Current subject UUID prefix or label",
            "Préfixe UUID ou étiquette du sujet actuel",
        ),
    ),
    predicate: Optional[str] = typer.Argument(
        None,
        metavar="PREDIKATO",
        help=tr_multi(
            "Nuna predikato ID aŭ parta nomo (malplena = elekti)",
            "Current predicate ID or partial name (empty = pick)",
            "ID du prédicat actuel ou nom partiel (vide = choisir)",
        ),
    ),
    object: Optional[str] = typer.Argument(  # noqa: A002
        None,
        metavar="OBJEKTO",
        help=tr_multi(
            "Nuna objekta valoro (malplena = elekti)",
            "Current object value (empty = pick)",
            "Valeur actuelle de l'objet (vide = choisir)",
        ),
    ),
    nova_subjekto: Optional[str] = typer.Option(
        None, "--nova-subjekto", "-ns",
        help=tr_multi(
            "Nova subjekto UUID-prefikso",
            "New subject UUID prefix",
            "Nouveau préfixe UUID du sujet",
        ),
    ),
    new_subject: Optional[str] = typer.Option(
        None, "--new-subject", hidden=True,
        help=tr_multi(
            "Nova subjekto UUID-prefikso",
            "New subject UUID prefix",
            "Nouveau préfixe UUID du sujet",
        ),
    ),
    nova_predikato: Optional[str] = typer.Option(
        None, "--nova-predikato", "-np",
        help=tr_multi(
            "Nova predikato ID",
            "New predicate ID",
            "Nouvel ID du prédicat",
        ),
    ),
    new_predicate: Optional[str] = typer.Option(
        None, "--new-predicate", hidden=True,
        help=tr_multi(
            "Nova predikato ID",
            "New predicate ID",
            "Nouvel ID du prédicat",
        ),
    ),
    nova_objekto: Optional[str] = typer.Option(
        None, "--nova-objekto", "-no",
        help=tr_multi(
            "Nova objekta valoro",
            "New object value",
            "Nouvelle valeur de l'objet",
        ),
    ),
    new_object: Optional[str] = typer.Option(
        None, "--new-object", hidden=True,
        help=tr_multi(
            "Nova objekta valoro",
            "New object value",
            "Nouvelle valeur de l'objet",
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
    """Modifi arkon (forigi + re-aldoni).

    Identigu arkon per nunaj valoroj, specifu novajn valorojn per --new-* flagoj.
    Se oni ne specifas predikaton aŭ objekton, aperas interaktiva listo
    por elekti la arkon.
    """
    # Resolve deprecated aliases
    new_subject = resolve_deprecated(nova_subjekto, new_subject,
                                     "new-subject", "nova-subjekto")
    new_predicate = resolve_deprecated(nova_predikato, new_predicate,
                                       "new-predicate", "nova-predikato")
    new_object = resolve_deprecated(nova_objekto, new_object,
                                    "new-object", "nova-objekto")

    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # ── Interactive mode: partial args → show picker ───────────────
    if predicate is None or object is None:
        triple = pick_triple(
            triple_svc, node_svc, pred_svc,
            subject=subject, predicate=predicate, object=object,
        )
        if triple is None:
            raise typer.Exit(1)
        # Use picked triple as "old" values
        subject = triple["subject_uuid"]
        predicate = triple["predicate_id"]
        object = triple["object_value"]  # noqa: A002
        object_type = triple.get("object_type", "uri")
        # For modifi we only support URI-type modifications (backward compat)
        if object_type != "uri":
            error(tr_multi(
                "Nuntempe modifi nur subtenas URI-objektojn.",
                "Currently modifi only supports URI objects.",
                "Actuellement modifi ne supporte que les objets URI.",
            ))
            raise typer.Exit(1)

    # Resolve current triple
    try:
        subj_node = node_svc.resolve_uuid_prefix(subject)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua subjekto-prefikso: {e}",
            "Ambiguous subject prefix: {e}",
            "Préfixe sujet ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not subj_node:
        error(tr_multi(
            "Subjekto ne trovita: {s}",
            "Subject not found: {s}",
            "Sujet non trouvé : {s}",
        ).format(s=subject))
        raise typer.Exit(1)
    subject_uuid = subj_node["node_id"]

    # Current object is always URI for modifi (compound PK requirement)
    try:
        obj_node = node_svc.resolve_uuid_prefix(object)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua objekto-prefikso: {e}",
            "Ambiguous object prefix: {e}",
            "Préfixe objet ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not obj_node:
        error(tr_multi(
            "Objekto ne trovita: {o}",
            "Object not found: {o}",
            "Objet non trouvé : {o}",
        ).format(o=object))
        raise typer.Exit(1)
    object_uuid = obj_node["node_id"]

    existing = triple_svc.get_one(subject_uuid, predicate, object_uuid, "uri")
    if not existing:
        error(tr_multi("Arko ne trovita.", "Arc not found.", "Arc non trouvé."))
        raise typer.Exit(1)

    # Determine new values (keep old if not specified)
    new_subj = new_subject or subject
    new_pred = new_predicate or predicate
    new_obj = new_object or object

    # Resolve new values
    try:
        new_subj_node = node_svc.resolve_uuid_prefix(new_subj)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua nova subjekto-prefikso: {e}",
            "Ambiguous new subject prefix: {e}",
            "Préfixe nouveau sujet ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not new_subj_node:
        error(tr_multi(
            "Nova subjekto ne trovita: {s}",
            "New subject not found: {s}",
            "Nouveau sujet non trouvé : {s}",
        ).format(s=new_subj))
        raise typer.Exit(1)
    new_subj_uuid = new_subj_node["node_id"]

    if new_obj is None:
        new_obj = object or ""
    try:
        new_obj_node = node_svc.resolve_uuid_prefix(new_obj)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua nova objekto-prefikso: {e}",
            "Ambiguous new object prefix: {e}",
            "Préfixe nouvel objet ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not new_obj_node:
        error(tr_multi(
            "Nova objekto ne trovita: {o}",
            "New object not found: {o}",
            "Nouvel objet non trouvé : {o}",
        ).format(o=new_obj))
        raise typer.Exit(1)
    new_obj_uuid = new_obj_node["node_id"]

    # Show preview
    if not yes:
        table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
        table.add_column("", no_wrap=True)
        table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
        table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
        table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=True)

        old_subj_label = resolve_node_label(node_svc, subject)
        old_pred_label = resolve_predicate_label(pred_svc, predicate)
        old_obj_label = resolve_node_label(node_svc, object)
        table.add_row(
            tr_multi("Malnova", "Old", "Ancien"),
            f"{old_subj_label} ({subject_uuid[:8]})",
            old_pred_label,
            f"{old_obj_label} ({object_uuid[:8]})",
        )
        new_subj_label = resolve_node_label(node_svc, new_subj)
        new_pred_label = resolve_predicate_label(pred_svc, new_pred)
        new_obj_label = resolve_node_label(node_svc, new_obj)
        table.add_row(
            tr_multi("Nova", "New", "Nouveau"),
            f"{new_subj_label} ({new_subj_uuid[:8]})",
            new_pred_label,
            f"{new_obj_label} ({new_obj_uuid[:8]})",
        )

        info("")
        info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu modifi tiun arkon? (forigi + re-aldoni)",
                "Modify this arc? (delete + re-add)",
                "Modifier cet arc ? (supprimer + ré-ajouter)",
            ),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Execute: delete + re-add in transaction
    from A_semantika.data.storage import now

    timestamp = now()
    with triple_svc.db.transaction() as conn:
        conn.execute(
            "DELETE FROM triples WHERE subject_uuid=? AND predicate_id=? "
            "AND object_value=? AND object_type='uri'",
            (subject_uuid, predicate, object_uuid),
        )
        conn.execute(
            """INSERT INTO triples (subject_uuid, predicate_id, object_type,
                                    object_value, kreita_je)
               VALUES (?, ?, 'uri', ?, ?)""",
            (new_subj_uuid, new_pred, new_obj_uuid, timestamp),
        )

    info(tr_multi(
        "Arko modifita: {s} --{p}--> {o}",
        "Arc modified: {s} --{p}--> {o}",
        "Arc modifié : {s} --{p}--> {o}",
    ).format(s=new_subj_uuid[:8], p=new_pred, o=new_obj_uuid[:8]))
