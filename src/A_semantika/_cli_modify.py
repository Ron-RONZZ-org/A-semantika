"""Modifi command for root triple operations.

Extracted from _cli_triples.py to keep each file under 500 lines.
Supports both URI and literal triples.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika._cli_helpers import (
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


def _build_modify_preview(
    node_svc,
    pred_svc,
    subject_uuid: str,
    predicate: str,
    object_value: str,
    object_type: str,
    object_lang: str | None,
    new_subj_uuid: str,
    new_pred: str,
    new_obj_value: str,
    new_obj_type: str,
    new_obj_lang: str | None,
) -> Table:
    """Build a preview table for modifi showing old → new values.

    Handles both URI and literal object types.
    """
    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column("", no_wrap=True)
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=True)

    old_subj_label = resolve_node_label(node_svc, subject_uuid)

    def _obj_display(val: str, typ: str, lang: str | None) -> str:
        if typ == "uri":
            return f"{resolve_node_label(node_svc, val)} ({val[:16]})"
        if lang:
            return f'"{val}"@{lang}'
        return f'"{val}"'

    old_pred_label = resolve_predicate_label(pred_svc, predicate)
    old_obj_display = _obj_display(object_value, object_type, object_lang)
    table.add_row(
        tr_multi("Malnova", "Old", "Ancien"),
        f"{old_subj_label} ({subject_uuid[:16]})",
        old_pred_label,
        old_obj_display,
    )

    new_subj_label = resolve_node_label(node_svc, new_subj_uuid)
    new_pred_label = resolve_predicate_label(pred_svc, new_pred)
    new_obj_display = _obj_display(new_obj_value, new_obj_type, new_obj_lang)
    table.add_row(
        tr_multi("Nova", "New", "Nouveau"),
        f"{new_subj_label} ({new_subj_uuid[:16]})",
        new_pred_label,
        new_obj_display,
    )

    return table


def _find_triple_direct(
    triple_svc, node_svc, subject_uuid: str, predicate: str, object: str,
) -> tuple[dict | None, str, str | None]:
    """Find an existing triple in direct mode (full SPO specified).

    Tries URI match first (resolving object as a node reference), then
    literal match.

    Returns:
        Tuple of (triple_dict or None, resolved_object_type, resolved_object_lang).
    """
    # Try URI: resolve object as node
    try:
        obj_node = node_svc.resolve_uuid_prefix(object)
    except AmbiguousUUIDError:
        obj_node = None

    if obj_node:
        existing = triple_svc.get_one(subject_uuid, predicate, obj_node["node_id"], "uri")
        if existing:
            return existing, "uri", None
    else:
        obj_node = None

    # Try literal match by subject + predicate + object_value
    results = triple_svc.search_triples(
        subject_uuids=[subject_uuid],
        predicate_ids=[predicate],
        object_values=[object],
        limit=2,
    )
    if results:
        t = results[0]
        return t, t.get("object_type", "literal"), t.get("object_lang")

    # Last resort: try with raw object as URI (for object that matched UUID
    # but was not a triple with object_type='uri')
    if obj_node:
        # Try searching by node_id regardless of type
        results = triple_svc.search_triples(
            subject_uuids=[subject_uuid],
            predicate_ids=[predicate],
            object_values=[obj_node["node_id"]],
            limit=2,
        )
        if results:
            t = results[0]
            return t, t.get("object_type", "uri"), t.get("object_lang")

    return None, "uri", None


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

        # Keep old values for no-op check
        old_object_type = object_type
        old_object_value = object
        old_object_lang = object_lang
    else:
        # ── Direct mode: full triplet provided ────────────────────
        # Resolve subject
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

        # Try to find existing triple (URI or literal)
        existing, old_object_type, old_object_lang = _find_triple_direct(
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
    new_obj_raw = new_object or old_object_value

    # Resolve new subject UUID
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

    # Resolve new object (URI → node lookup, literal → raw value)
    new_obj_value: str = new_obj_raw
    new_obj_lang: str | None = lingvo if str_ else None
    if new_object_type == "uri":
        new_obj_raw_clean = new_obj_raw if new_obj_raw is not None else (old_object_value or "")
        try:
            new_obj_node = node_svc.resolve_uuid_prefix(new_obj_raw_clean)
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
        table = _build_modify_preview(
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
