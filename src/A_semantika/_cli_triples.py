"""Root triple CLI commands: aldoni, forigi.

Extracted into separate files to keep each file under 500 lines:
  - _cli_helpers.py: shared helpers (pick_triple, type flag validation)
  - _cli_modify.py: modifi command
  - _cli_query.py: serci, vidi, eksporti commands
"""
from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr_multi
from A_semantika._cli_helpers import pick_triple, validate_type_flags
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import confirm_triple, resolve_node_label, resolve_predicate_label
from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_triple_service,
)


# ── Root triple commands ──────────────────────────────────────────────


def aldoni(
    subject: str = typer.Argument(
        ...,
        metavar="SUBJEKTO",
        help=tr_multi(
            "Subjekto UUID-prefikso",
            "Subject UUID prefix",
            "Préfixe UUID du sujet",
        ),
    ),
    predicate: str = typer.Argument(
        ...,
        metavar="PREDIKATO",
        help=tr_multi("Predikato ID", "Predicate ID", "ID du prédicat"),
    ),
    object: str = typer.Argument(  # noqa: A002
        ...,
        metavar="OBJEKTO",
        help=tr_multi(
            "Objekta valoro",
            "Object value",
            "Valeur de l'objet",
        ),
    ),
    str_: bool = typer.Option(
        False, "-s", "--str",
        help=tr_multi(
            "Objekto estas teksta literal (not URI)",
            "Object is a string literal (not URI)",
            "L'objet est un littéral textuel (pas URI)",
        ),
    ),
    int_: bool = typer.Option(
        False, "--int",
        help=tr_multi(
            "Objekto estas entjera literal (not URI)",
            "Object is an integer literal (not URI)",
            "L'objet est un littéral entier (pas URI)",
        ),
    ),
    float_: bool = typer.Option(
        False, "-f", "--float",
        help=tr_multi(
            "Objekto estas flosanta literal (not URI)",
            "Object is a float literal (not URI)",
            "L'objet est un littéral flottant (pas URI)",
        ),
    ),
    bool_: bool = typer.Option(
        False, "-b", "--bool",
        help=tr_multi(
            "Objekto estas bulea literal (not URI)",
            "Object is a boolean literal (not URI)",
            "L'objet est un littéral booléen (pas URI)",
        ),
    ),
    lingvo: Optional[str] = typer.Option(
        None, "-l", "--lingvo",
        help=tr_multi(
            "Lingva etikedo (nur kun --str)",
            "Language tag (only with --str)",
            "Étiquette de langue (seulement avec --str)",
        ),
    ),
    unuo: Optional[str] = typer.Option(
        None, "-u", "--unuo",
        help=tr_multi(
            "Unuo UUID por nombraj valoroj (nur --int/--float)",
            "Unit UUID for numeric values (only --int/--float)",
            "UUID d'unité pour valeurs numériques (seulement --int/--float)",
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
    """Aldoni semantikan arkon: subjekto --predikato--> objekto.

    Defaŭlte objekto estas URI referenco (nod UUID). Uzu --str por teksta literal.
    """
    datatype = validate_type_flags(str_, int_, float_, bool_, lingvo, unuo)
    object_type = "literal" if (str_ or int_ or float_ or bool_) else "uri"

    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Resolve subject UUID
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
    subject_uuid = subj_node["uuid"]

    # Resolve object UUID if URI type
    object_uuid = object
    if object_type == "uri":
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
        object_uuid = obj_node["uuid"]

    # Validate predicate exists (BEFORE confirmation preview)
    if not pred_svc.get_by_predicate_id(predicate):
        error(tr_multi(
            "Predikato ne trovita: {p}",
            "Predicate not found: {p}",
            "Prédicat non trouvé : {p}",
        ).format(p=predicate))
        raise typer.Exit(1)

    # Confirm
    if not confirm_triple(
        node_svc, pred_svc,
        subject_uuid, predicate, object_uuid,
        object_type, lingvo, datatype, unuo,
        yes=yes,
    ):
        info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
        raise typer.Exit(0)
        error(tr_multi(
            "Predikato ne trovita: {p}",
            "Predicate not found: {p}",
            "Prédicat non trouvé : {p}",
        ).format(p=predicate))
        raise typer.Exit(1)

    try:
        triple_svc.add(
            subject_uuid=subject_uuid,
            predicate_id=predicate,
            object_value=object_uuid,
            object_type=object_type,
            object_lang=lingvo if str_ else None,
            object_datatype=datatype,
            object_unit=unuo,
        )
        info(tr_multi(
            "Arko kreita: {s} --{p}--> {o}",
            "Arc created: {s} --{p}--> {o}",
            "Arc créé : {s} --{p}--> {o}",
        ).format(
            s=subject_uuid[:8], p=predicate, o=object_uuid[:8],
        ))
    except ValueError as e:
        error(tr_multi(
            "Eraro: {e}", "Error: {e}", "Erreur : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e


def forigi(
    subject: str = typer.Argument(
        ...,
        metavar="SUBJEKTO",
        help=tr_multi(
            "Subjekto UUID-prefikso aŭ etikedo",
            "Subject UUID prefix or label",
            "Préfixe UUID ou étiquette du sujet",
        ),
    ),
    predicate: Optional[str] = typer.Argument(
        None,
        metavar="PREDIKATO",
        help=tr_multi(
            "Predikato ID aŭ parta nomo (malplena = elekti)",
            "Predicate ID or partial name (empty = pick)",
            "ID du prédicat ou nom partiel (vide = choisir)",
        ),
    ),
    object: Optional[str] = typer.Argument(  # noqa: A002
        None,
        metavar="OBJEKTO",
        help=tr_multi(
            "Objekta valoro (malplena = elekti)",
            "Object value (empty = pick)",
            "Valeur de l'objet (vide = choisir)",
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
    """Forigi semantikan arkon.

    Se oni ne specifas predikaton aŭ objekton, aperas interaktiva listo
    por elekti la forigotan arkon.
    """
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

        if not yes:
            subj_label = resolve_node_label(node_svc, triple["subject_uuid"])
            obj_label = (
                resolve_node_label(node_svc, triple["object_value"])
                if triple["object_type"] == "uri"
                else triple["object_value"]
            )
            pred_label = resolve_predicate_label(pred_svc, triple["predicate_id"])

            from A.utils.interactive import confirm_action

            if not confirm_action(
                tr_multi(
                    f"Ĉu forigi arkon: {subj_label} --{pred_label}--> {obj_label}?",
                    f"Delete arc: {subj_label} --{pred_label}--> {obj_label}?",
                    f"Supprimer l'arc : {subj_label} --{pred_label}--> {obj_label}?",
                ),
                default=False,
            ):
                info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
                raise typer.Exit(0)

        deleted = triple_svc.remove(
            subject_uuid=triple["subject_uuid"],
            predicate_id=triple["predicate_id"],
            object_value=triple["object_value"],
            object_type=triple.get("object_type", "uri"),
        )
        if deleted:
            info(tr_multi("Arko forigita.", "Arc deleted.", "Arc supprimé."))
        else:
            info(tr_multi("Neniu arko trovita.", "No arc found.", "Aucun arc trouvé."))
        return

    # ── Direct mode: full triplet provided (backward compat) ──────
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

    if not yes:
        obj_label = resolve_node_label(node_svc, object)
        subj_label = resolve_node_label(node_svc, subject)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                f"Ĉu forigi arkon: {subj_label} --{predicate}--> {obj_label}?",
                f"Delete arc: {subj_label} --{predicate}--> {obj_label}?",
                f"Supprimer l'arc : {subj_label} --{predicate}--> {obj_label}?",
            ),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    deleted = triple_svc.remove(
        subject_uuid=subj_node["uuid"],
        predicate_id=predicate,
        object_value=obj_node["uuid"],
        object_type="uri",
    )
    if deleted:
        info(tr_multi("Arko forigita.", "Arc deleted.", "Arc supprimé."))
    else:
        info(tr_multi("Neniu arko trovita.", "No arc found.", "Aucun arc trouvé."))
