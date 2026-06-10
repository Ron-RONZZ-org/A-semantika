"""Root triple CLI command: aldoni.

``forigi`` lives in ``_cli_triple_forigi.py``.

Extracted into separate files to keep each file under 500 lines:
  - _cli_helpers.py: shared helpers (pick_triple, type flag validation)
  - _cli_modify.py: modifi command
  - _cli_query.py: serci, vidi, eksporti commands
  - _cli_triple_forigi.py: forigi command (extracted from this file)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from A import error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._cli_helpers import resolve_deprecated, validate_type_flags
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._predicate_service import AmbiguousPredicateError
from A_semantika._preview import build_metadata_diff_table, confirm_triple
from A_semantika._triple_service import DuplicateTripleError
from A_semantika._unit_errors import UnitNotFoundError
from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_triple_service,
    get_unit_service,
)


# ── Helpers ─────────────────────────────────────────────────────────────


def _handle_duplicate_triple(
    triple_svc,
    subject_uuid: str,
    predicate_id: str,
    object_value: str,
    object_type: str,
    object_lang: str | None,
    object_datatype: str | None,
    object_unit: str | None,
    yes: bool,
) -> None:
    """Handle duplicate triple: show metadata diff and offer update.

    Called when ``triple_svc.add()`` raises ``DuplicateTripleError``.
    Computes which metadata columns (lang, datatype, unit) differ,
    shows a compact diff table, and asks the user to confirm the update.

    With ``yes=True``, silently auto-updates if metadata differs.
    """
    existing = triple_svc.get_one(subject_uuid, predicate_id, object_value, object_type)
    if not existing:
        error(tr_multi(
            "Ne povis preni la ekzistantan arkon.",
            "Could not retrieve existing triple.",
            "Impossible de récupérer le triplet existant.",
        ))
        raise typer.Exit(1)

    # Build changes: only track columns that were explicitly provided
    changes: dict[str, str | None] = {}
    if object_lang is not None and object_lang != existing.get("object_lang"):
        changes["object_lang"] = object_lang
    if object_datatype is not None and object_datatype != existing.get("object_datatype"):
        changes["object_datatype"] = object_datatype
    if object_unit is not None and object_unit != existing.get("object_unit"):
        changes["object_unit"] = object_unit

    if not changes:
        info(tr_multi(
            "Arko jam ekzistas kun samaj metadatumoj.",
            "Triple already exists with identical metadata.",
            "Le triplet existe déjà avec les mêmes métadonnées.",
        ))
        raise typer.Exit(0)

    # Show preview (skip if -y)
    if not yes:
        table = build_metadata_diff_table(
            existing,
            object_lang=changes.get("object_lang"),
            object_datatype=changes.get("object_datatype"),
            object_unit=changes.get("object_unit"),
        )
        if table:
            info("")
            info(table)

        if not confirm_action(
            tr_multi(
                "Ĉu ĝisdatigi la metadatumojn de la ekzistanta arko?",
                "Update the metadata of the existing arc?",
                "Mettre à jour les métadonnées de l'arc existant ?",
            ),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Apply metadata update
    updated = triple_svc.update_metadata(
        subject_uuid, predicate_id, object_value, object_type,
        object_lang=changes.get("object_lang"),
        object_datatype=changes.get("object_datatype"),
        object_unit=changes.get("object_unit"),
    )
    if updated:
        info(tr_multi("Arko ĝisdatigita.", "Arc updated.", "Arc mis à jour."))
    raise typer.Exit(0)


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
        None, "--str-dosiero", "-D",
        help=tr_multi(
            "Legu dosieron kiel tekstan literal (anstataŭ OBJEKTO)",
            "Read file as string literal (instead of OBJEKTO)",
            "Lire le fichier comme un littéral textuel (au lieu de OBJEKTO)",
        ),
    ),
    str_dosiero_old: Optional[str] = typer.Option(
        None, "-d", hidden=True,
        help=tr_multi(
            "Legu dosieron kiel tekstan literal (anstataŭ OBJEKTO) — malrekomendita, uzu -D",
            "Read file as string literal (instead of OBJEKTO) — deprecated, use -D",
            "Lire le fichier comme un littéral textuel (au lieu de OBJEKTO) — déprécié, utilisez -D",
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
    katex: Optional[str] = typer.Option(
        None, "--katex", "-K",
        help=tr_multi(
            "KaTeX formulo (kun aŭ sen $...$ delimitiloj)",
            "KaTeX formula (with or without $...$ delimiters)",
            "Formule KaTeX (avec ou sans délimiteurs $...$)",
        ),
    ),
    kodbloko: Optional[str] = typer.Option(
        None, "--kodbloko",
        hidden=True,
        help=tr_multi(
            "Malrekomendita: uzu --str-dosiero --kodlingvo <lingvo>",
            "Deprecated: use --str-dosiero --kodlingvo <language>",
            "Déprécié : utilisez --str-dosiero --kodlingvo <langue>",
        ),
    ),
    kodlingvo: Optional[str] = typer.Option(
        None, "--kodlingvo", "-L",
        help=tr_multi(
            "Programlingvo por kodbloko el --str-dosiero aŭ --str (ekz. python, qd)",
            "Programming language for code from --str-dosiero or --str (e.g. python, qd)",
            "Langage de programmation pour code depuis --str-dosiero ou --str (ex. python, qd)",
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
    --str-dosiero/-D por legi dosieron kiel tekstan literal.
    Uzu --katex/-k por KaTeX formulo, --str-dosiero/-D kun --kodlingvo/-L por kodbloko
    el dosiero, aŭ --str -L por unulinia kodaĵeto.

    Se la objekta valoro komenciĝas per -, uzu -- antaŭ ĝi por eviti
    misinterpretadon kiel flago: aldoni NODO predikato -f -- -1.5
    """
    # Resolve deprecated -d -> -D alias
    str_dosiero = resolve_deprecated(str_dosiero, str_dosiero_old, "d", "D")

    # --kodbloko is deprecated: redirect to --str-dosiero with --kodlingvo
    if kodbloko is not None:
        warning(tr_multi(
            "--kodbloko estas malrekomendita, uzu --str-dosiero --kodlingvo <lingvo>",
            "--kodbloko is deprecated, use --str-dosiero --kodlingvo <language>",
            "--kodbloko est déprécié, utilisez --str-dosiero --kodlingvo <langue>",
        ))
        if kodlingvo is None:
            kodlingvo = "plain"
        str_dosiero = kodbloko
        kodbloko = None  # Fall through to str_dosiero logic

    # --katex and --str-dosiero/OBJEKTO are mutually exclusive
    if katex is not None and (object is not None or str_dosiero is not None):
        error(tr_multi(
            "Ne eblas uzi samtempe --katex kun OBJEKTO aŭ --str-dosiero",
            "Cannot use --katex with OBJEKTO or --str-dosiero",
            "Impossible d'utiliser --katex avec OBJEKTO ou --str-dosiero",
        ))
        raise typer.Exit(1)

    # --str-dosiero and OBJEKTO are mutually exclusive
    if str_dosiero is not None and object is not None:
        error(tr_multi(
            "Ne eblas uzi samtempe OBJEKTO kaj --str-dosiero",
            "Cannot use both OBJEKTO and --str-dosiero",
            "Impossible d'utiliser OBJEKTO et --str-dosiero a la fois",
        ))
        raise typer.Exit(1)

    # Determine object value source
    if katex is not None:
        # --katex: strip $...$ delimiters, store raw formula
        formula = katex.strip()
        if formula.startswith("$$") and formula.endswith("$$"):
            formula = formula[2:-2].strip()
        elif formula.startswith("$") and formula.endswith("$"):
            formula = formula[1:-1].strip()
        if not formula:
            error(tr_multi(
                "Malplena KaTeX formulo",
                "Empty KaTeX formula",
                "Formule KaTeX vide",
            ))
            raise typer.Exit(1)
        object_value = formula
        katex_flag = True
        kodlingvo_val = None  # kodlingvo is irrelevant for KaTeX
    elif str_dosiero is not None:
        # --str-dosiero/-D: read file as string literal (implies --str)
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
        katex_flag = False
        kodlingvo_val = kodlingvo
    elif object is not None:
        object_value = object
        katex_flag = False
        kodlingvo_val = kodlingvo
    else:
        error(tr_multi(
            "Bezonas OBJEKTO, --katex, aŭ --str-dosiero",
            "Requires OBJEKTO, --katex, or --str-dosiero",
            "Nécessite OBJEKTO, --katex, ou --str-dosiero",
        ))
        raise typer.Exit(1)

    datatype, object_type = validate_type_flags(
        str_, int_, float_, bool_, lingvo, unuo,
        katex=katex_flag, kodlingvo=kodlingvo_val,
    )

    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Validate unit: resolve via UnitService (node_id → symbol → expression)
    if unuo:
        try:
            unuo = get_unit_service().resolve_unit(unuo)
        except UnitNotFoundError as e:
            error(tr_multi(
                "Unuo ne trovita: {u}",
                "Unit not found: {u}",
                "Unité non trouvée : {u}",
            ).format(u=str(e)))
            raise typer.Exit(1) from e

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
        # Display: URI → truncated, code block → compact MIME+chars,
        # other literals → truncated to keep log line on one terminal line
        if object_type == "uri":
            o_display = truncate_uuid(object_uuid)
        elif datatype and (datatype.startswith("text/") or datatype.startswith("application/")):
            o_display = f"{datatype}, {len(object_uuid)} chars"
        else:
            o_display = object_uuid[:80] + "..." if len(object_uuid) > 80 else object_uuid
        s_display = truncate_uuid(subject_uuid) if isinstance(subject_uuid, str) else subject_uuid
        info(tr_multi(
            "Arko kreita: {s} --{p}--> {o}",
            "Arc created: {s} --{p}--> {o}",
            "Arc créé : {s} --{p}--> {o}",
        ).format(
            s=s_display, p=predicate_id, o=o_display,
        ))
    except DuplicateTripleError:
        # Triple already exists — offer metadata update
        _handle_duplicate_triple(
            triple_svc,
            subject_uuid, predicate_id, object_uuid, object_type,
            lingvo if str_ else None, datatype, unuo,
            yes,
        )
    except ValueError as e:
        error(tr_multi(
            "Eraro: {e}", "Error: {e}", "Erreur : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
