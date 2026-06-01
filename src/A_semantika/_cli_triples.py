"""Root triple CLI commands: aldoni, forigi.

Extracted into separate files to keep each file under 500 lines:
  - _cli_helpers.py: shared helpers (pick_triple, type flag validation)
  - _cli_modify.py: modifi command
  - _cli_query.py: serci, vidi, eksporti commands
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from A import error, info, tr_multi
from A_semantika._cli_helpers import (
    _find_triple_by_spo,
    pick_triple,
    validate_type_flags,
)
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError, NodeService
from A_semantika._predicate_service import AmbiguousPredicateError
from A_semantika._preview import confirm_triple, resolve_node_label, resolve_predicate_label
from A_semantika._triple_service import TripleService
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
    object: Optional[str] = typer.Argument(  # noqa: A002
        None,
        metavar="OBJEKTO",
        help=tr_multi(
            "Objekta valoro (uzu -- antaŭ valoroj komencantaj per -)",
            "Object value (use -- before values starting with -)",
            "Valeur de l'objet (utilisez -- avant les valeurs commençant par -)",
        ),
    ),
    str_dosiero: Optional[str] = typer.Option(
        None, "--str-dosiero", "-d",
        help=tr_multi(
            "Legu dosieron kiel tekstan literal (anstataŭ OBJEKTO)",
            "Read file as string literal (instead of OBJEKTO)",
            "Lire le fichier comme un littéral textuel (au lieu de OBJEKTO)",
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
        False, "-i", "--int",
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
            "Lingva etikedo (nur kun --str aŭ --str-dosiero)",
            "Language tag (only with --str or --str-dosiero)",
            "Étiquette de langue (seulement avec --str ou --str-dosiero)",
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

    Defaŭlte objekto estas URI referenco (nod UUID). Uzu --str por teksta literal,
    --str-dosiero por legi dosieron kiel tekstan literal.

    Se la objekta valoro komenciĝas per -, uzu -- antaŭ ĝi por eviti
    misinterpretadon kiel flago: aldoni NODO predikato -f -- -1.5
    """
    # Handle -d/--str-dosiero: read file content as string literal
    if str_dosiero is not None and object is not None:
        error(tr_multi(
            "Ne eblas uzi samtempe OBJEKTO kaj --str-dosiero",
            "Cannot use both OBJEKTO and --str-dosiero",
            "Impossible d'utiliser OBJEKTO et --str-dosiero à la fois",
        ))
        raise typer.Exit(1)
    if str_dosiero is not None:
        # --str-dosiero implies --str (string literal)
        str_ = True
        file_path = Path(str_dosiero)
        try:
            content = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            error(tr_multi(
                "Dosiero ne trovita: {f}",
                "File not found: {f}",
                "Fichier non trouvé : {f}",
            ).format(f=str_dosiero))
            raise typer.Exit(1) from None
        except IsADirectoryError:
            error(tr_multi(
                "{f} estas dosierujo, ne dosiero",
                "{f} is a directory, not a file",
                "{f} est un dossier, pas un fichier",
            ).format(f=str_dosiero))
            raise typer.Exit(1) from None
        except UnicodeDecodeError:
            error(tr_multi(
                "{f} ne estas valida UTF-8 dosiero",
                "{f} is not a valid UTF-8 file",
                "{f} n'est pas un fichier UTF-8 valide",
            ).format(f=str_dosiero))
            raise typer.Exit(1) from None
        object_value = content
    elif object is None:
        error(tr_multi(
            "Bezonas OBJEKTO aŭ --str-dosiero",
            "Requires OBJEKTO or --str-dosiero",
            "Nécessite OBJEKTO ou --str-dosiero",
        ))
        raise typer.Exit(1)
    else:
        object_value = object

    datatype, object_type = validate_type_flags(str_, int_, float_, bool_, lingvo, unuo)

    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Resolve subject UUID (prefix → substring fallback)
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
        # Fallback: substring match (user may have typed middle of ID)
        try:
            subj_node = node_svc.resolve_node_id_substring(subject)
        except AmbiguousUUIDError as e:
            error(tr_multi(
                "Ambigua subjekto: {e}",
                "Ambiguous subject: {e}",
                "Sujet ambigu : {e}",
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

    # Resolve object UUID if URI type (prefix → substring fallback)
    object_uuid = object_value
    if object_type == "uri":
        try:
            obj_node = node_svc.resolve_node_id_prefix(object_value)
        except AmbiguousUUIDError as e:
            error(tr_multi(
                "Ambigua objekto-prefikso: {e}",
                "Ambiguous object prefix: {e}",
                "Préfixe objet ambigu : {e}",
            ).format(e=str(e)))
            raise typer.Exit(1) from e
        if not obj_node:
            # Fallback: substring match
            try:
                obj_node = node_svc.resolve_node_id_substring(object_value)
            except AmbiguousUUIDError as e:
                error(tr_multi(
                    "Ambigua objekto: {e}",
                    "Ambiguous object: {e}",
                    "Objet ambigu : {e}",
                ).format(e=str(e)))
                raise typer.Exit(1) from e
        if not obj_node:
            error(tr_multi(
                "Objekto ne trovita: {o}",
                "Object not found: {o}",
                "Objet non trouvé : {o}",
            ).format(o=object_value))
            raise typer.Exit(1)
        object_uuid = obj_node["node_id"]

    # Resolve predicate ID (supports prefix matching)
    try:
        pred = pred_svc.resolve_predicate_id_prefix(predicate)
    except AmbiguousPredicateError as e:
        error(tr_multi(
            "Ambigua predikato-prefikso: {e}",
            "Ambiguous predicate prefix: {e}",
            "Préfixe prédicat ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not pred:
        error(tr_multi(
            "Predikato ne trovita: {p}",
            "Predicate not found: {p}",
            "Prédicat non trouvé : {p}",
        ).format(p=predicate))
        raise typer.Exit(1)
    predicate_id = pred["predicate_id"]  # Use resolved full ID

    # Confirm
    if not confirm_triple(
        node_svc, pred_svc,
        subject_uuid, predicate_id, object_uuid,
        object_type, lingvo, datatype, unuo,
        yes=yes,
    ):
        info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
        raise typer.Exit(0)

    try:
        triple_svc.add(
            subject_uuid=subject_uuid,
            predicate_id=predicate_id,
            object_value=object_uuid,
            object_type=object_type,
            object_lang=lingvo if str_ else None,
            object_datatype=datatype,
            object_unit=unuo,
        )
        # Display: URI object values get context-aware truncation; literal values stay full
        o_display = truncate_uuid(object_uuid) if object_type == "uri" else object_uuid
        s_display = truncate_uuid(subject_uuid) if isinstance(subject_uuid, str) else subject_uuid
        info(tr_multi(
            "Arko kreita: {s} --{p}--> {o}",
            "Arc created: {s} --{p}--> {o}",
            "Arc créé : {s} --{p}--> {o}",
        ).format(
            s=s_display, p=predicate_id, o=o_display,
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
        subj_node = node_svc.resolve_node_id_prefix(subject)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua subjekto-prefikso: {e}",
            "Ambiguous subject prefix: {e}",
            "Préfixe sujet ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not subj_node:
        # Fallback: substring match
        try:
            subj_node = node_svc.resolve_node_id_substring(subject)
        except AmbiguousUUIDError as e:
            error(tr_multi(
                "Ambigua subjekto: {e}",
                "Ambiguous subject: {e}",
                "Sujet ambigu : {e}",
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

    # Find triple (try URI first, then literal)
    triple = _find_triple_by_spo(
        triple_svc, node_svc, subject_uuid, predicate, object,
    )
    if not triple:
        error(tr_multi(
            "Arko ne trovita.",
            "Arc not found.",
            "Arc non trouvé.",
        ))
        raise typer.Exit(1)

    obj_value = triple["object_value"]
    obj_type = triple.get("object_type", "uri")
    obj_lang = triple.get("object_lang")

    if not yes:
        obj_label = (
            resolve_node_label(node_svc, obj_value)
            if obj_type == "uri"
            else obj_value
        )
        subj_label = resolve_node_label(node_svc, subject_uuid)

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
        subject_uuid=subject_uuid,
        predicate_id=predicate,
        object_value=obj_value,
        object_type=obj_type,
    )
    if deleted:
        info(tr_multi("Arko forigita.", "Arc deleted.", "Arc supprimé."))
    else:
        info(tr_multi("Neniu arko trovita.", "No arc found.", "Aucun arc trouvé."))
