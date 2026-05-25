"""Modifi command for root triple operations.

Extracted from _cli_triples.py to keep each file under 500 lines.
Supports both URI and literal triples.
"""
from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr_multi
from A_semantika._cli_helpers import (
    build_modify_preview,
    find_triple_direct,
    pick_triple,
    resolve_deprecated,
    validate_type_flags,
)
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
    str_: bool = typer.Option(
        False, "-s", "--str",
        help=tr_multi(
            "Nova objekto estas teksta literal",
            "New object is a string literal",
            "Le nouvel objet est un littéral textuel",
        ),
    ),
    int_: bool = typer.Option(
        False, "--int",
        help=tr_multi(
            "Nova objekto estas entjera literal",
            "New object is an integer literal",
            "Le nouvel objet est un littéral entier",
        ),
    ),
    float_: bool = typer.Option(
        False, "-f", "--float",
        help=tr_multi(
            "Nova objekto estas flosanta literal",
            "New object is a float literal",
            "Le nouvel objet est un littéral flottant",
        ),
    ),
    bool_: bool = typer.Option(
        False, "-b", "--bool",
        help=tr_multi(
            "Nova objekto estas bulea literal",
            "New object is a boolean literal",
            "Le nouvel objet est un littéral booléen",
        ),
    ),
    lingvo: Optional[str] = typer.Option(
        None, "-l", "--lingvo",
        help=tr_multi(
            "Lingva etikedo por nova objekto (nur kun --str)",
            "Language tag for new object (only with --str)",
            "Étiquette de langue pour le nouvel objet (seulement avec --str)",
        ),
    ),
    unuo: Optional[str] = typer.Option(
        None, "-u", "--unuo",
        help=tr_multi(
            "Unuo UUID por nova nombra valoro (nur --int/--float)",
            "Unit UUID for new numeric value (only --int/--float)",
            "UUID d'unité pour nouvelle valeur numérique (seulement --int/--float)",
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

    Por ŝanĝi objekton al ne-URI literal, uzu --str, --int, --float, aŭ --bool.
    Defaŭlte nova objekto estas URI (nod-referenco).
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

    # Determine new object type from flags (default URI for backward compat)
    new_datatype = validate_type_flags(str_, int_, float_, bool_, lingvo, unuo)
    new_object_type = "literal" if (str_ or int_ or float_ or bool_) else "uri"

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
        object_lang = triple.get("object_lang")

        # Resolve old subject
        try:
            subj_node = node_svc.resolve_node_id_prefix(subject)
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

        # Keep old values for no-op check
        old_object_type = object_type
        old_object_value = object
        old_object_lang = object_lang
    else:
        # ── Direct mode: full triplet provided ────────────────────
        # Resolve subject
        try:
            subj_node = node_svc.resolve_node_id_prefix(subject)
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

        # Try to find existing triple (URI or literal)
        existing, old_object_type, old_object_lang = find_triple_direct(
            triple_svc, node_svc, subject_uuid, predicate, object,
        )
        if not existing:
            error(tr_multi(
                "Arko ne trovita.",
                "Arc not found.",
                "Arc non trouvé.",
            ))
            raise typer.Exit(1)

        old_object_value = existing["object_value"]
        old_object_lang = old_object_lang or existing.get("object_lang")

    # ── Resolve new values ────────────────────────────────────────
    new_subj = new_subject or subject
    new_pred = new_predicate or predicate
    new_obj_raw = new_object if new_object is not None else old_object_value

    # Resolve new subject UUID
    try:
        new_subj_node = node_svc.resolve_node_id_prefix(new_subj)
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

    # Resolve new object (URI → node lookup, literal → raw value)
    new_obj_value: str = new_obj_raw
    new_obj_lang: str | None = lingvo if str_ else None
    if new_object_type == "uri":
        new_obj_raw_clean = new_obj_raw if new_obj_raw is not None else (old_object_value or "")
        try:
            new_obj_node = node_svc.resolve_node_id_prefix(new_obj_raw_clean)
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
            ).format(o=new_obj_raw_clean))
            raise typer.Exit(1)
        new_obj_value = new_obj_node["node_id"]

    # ── Preview & confirm ─────────────────────────────────────────
    if not yes:
        table = build_modify_preview(
            node_svc, pred_svc,
            subject_uuid, predicate, old_object_value,
            old_object_type, old_object_lang,
            new_subj_uuid, new_pred, new_obj_value,
            new_object_type, new_obj_lang,
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

    # ── No-op check ───────────────────────────────────────────────
    noop = (
        subject_uuid == new_subj_uuid
        and predicate == new_pred
        and old_object_value == new_obj_value
        and old_object_type == new_object_type
    )
    if noop:
        info(tr_multi(
            "Neniu ŝanĝo: arko restas neŝanĝita.",
            "No change: arc remains unchanged.",
            "Aucun changement : l'arc reste inchangé.",
        ))
        return

    # ── Execute: delete old + insert new ──────────────────────────
    # Validate FK references before removal to provide clear error
    # messages instead of cryptic SQLite constraint failures.
    subj_check = triple_svc.db.execute_one(
        "SELECT node_id FROM nodes WHERE node_id = ?", (new_subj_uuid,)
    )
    if not subj_check:
        error(tr_multi(
            "Nova subjekto ne trovita: {s}",
            "New subject not found: {s}",
            "Nouveau sujet non trouvé : {s}",
        ).format(s=new_subj_uuid))
        raise typer.Exit(1)

    pred_check = triple_svc.db.execute_one(
        "SELECT predicate_id FROM predicates WHERE predicate_id = ?", (new_pred,)
    )
    if not pred_check:
        error(tr_multi(
            "Nova predikato ne trovita: {p}",
            "New predicate not found: {p}",
            "Nouveau prédicat non trouvé : {p}",
        ).format(p=new_pred))
        raise typer.Exit(1)

    if new_object_type == "uri":
        obj_check = triple_svc.db.execute_one(
            "SELECT node_id FROM nodes WHERE node_id = ?", (new_obj_value,)
        )
        if not obj_check:
            error(tr_multi(
                "Nova objekto ne trovita: {o}",
                "New object not found: {o}",
                "Nouvel objet non trouvé : {o}",
            ).format(o=new_obj_value))
            raise typer.Exit(1)

    from A_semantika.data.storage import now

    timestamp = now()
    with triple_svc.db.transaction() as conn:
        conn.execute(
            "DELETE FROM triples WHERE subject_uuid=? AND predicate_id=? "
            "AND object_value=? AND object_type=?",
            (subject_uuid, predicate, old_object_value, old_object_type),
        )
        conn.execute(
            """INSERT INTO triples (subject_uuid, predicate_id, object_type,
                                    object_value, object_lang, object_datatype,
                                    kreita_je)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (new_subj_uuid, new_pred, new_object_type, new_obj_value,
             new_obj_lang, new_datatype, timestamp),
        )

    # ── Report success ────────────────────────────────────────────
    new_obj_display = new_obj_value[:16] if new_object_type == "uri" else f'"{new_obj_value}"'
    if new_object_type == "literal" and new_obj_lang:
        new_obj_display = f'"{new_obj_value}"@{new_obj_lang}'
    info(tr_multi(
        "Arko modifita: {s} --{p}--> {o} ({t})",
        "Arc modified: {s} --{p}--> {o} ({t})",
        "Arc modifié : {s} --{p}--> {o} ({t})",
    ).format(s=new_subj_uuid[:16], p=new_pred, o=new_obj_display,
             t=new_object_type))
