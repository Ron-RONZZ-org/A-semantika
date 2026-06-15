"""Modifi command for root triple operations.

Extracted from _cli_triples.py to keep each file under 500 lines.
Supports both URI and literal triples.
"""
from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr_multi, warning
from A_semantika._cli_helpers import (
    resolve_deprecated,
    validate_type_flags,
)
from A_semantika._cli_modify_preview import build_modify_preview
from A_semantika._modify_helpers import (
    execute_modification,
    format_new_object_display,
    resolve_new_object_source,
    resolve_new_object_value,
    resolve_subject_id,
)
from A_semantika._node_helpers import truncate_uuid
from A_semantika._triple_picker import resolve_triple
from A_semantika._unit_errors import UnitNotFoundError
from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_triple_service,
    get_unit_service,
)

# ── Main command ────────────────────────────────────────────────────────


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
            "Nuna predikato ID aŭ parta nomo (malplena = elekti; \\\"\\\" = wildcard)",
            "Current predicate ID or partial name (empty = pick; \\\"\\\" = wildcard)",
            "ID du prédicat actuel ou nom partiel (vide = choisir ; \\\"\\\" = wildcard)",
        ),
    ),
    object: Optional[str] = typer.Argument(  # noqa: A002
        None,
        metavar="OBJEKTO",
        help=tr_multi(
            "Nuna objekta valoro (malplena = elekti; \\\"\\\" = wildcard)",
            "Current object value (empty = pick; \\\"\\\" = wildcard)",
            "Valeur actuelle de l'objet (vide = choisir ; \\\"\\\" = wildcard)",
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
    str_dosiero: Optional[str] = typer.Option(
        None, "--str-dosiero", "-D",
        help=tr_multi(
            "Legu dosieron kiel tekstan literal (anstataŭ --nova-objekto)",
            "Read file as string literal (instead of --nova-objekto)",
            "Lire le fichier comme un littéral textuel (au lieu de --nova-objekto)",
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
    lingvo: Optional[str] = typer.Option(
        None, "-l", "--lingvo",
        help=tr_multi(
            "Lingva etikedo por nova objekto (nur kun --str aŭ --str-dosiero)",
            "Language tag for new object (only with --str or --str-dosiero)",
            "Étiquette de langue pour le nouvel objet (seulement avec --str ou --str-dosiero)",
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

    Identigu arkon per nunaj valoroj (subjekto, predikato, objekto —
    ĉiuj subtenas partajn etikedojn).  Specifu novajn valorojn per --new-* flagoj.
    Se oni ne specifas predikaton aŭ objekton, aperas interaktiva listo
    por elekti la arkon.  Uzu \\"\\" kiel wildcard por ajna kampo.

    Por ŝanĝi objekton al ne-URI literal, uzu --str, --int, --float, aŭ --bool.
    Defaŭlte nova objekto estas URI (nod-referenco).

    Por uzi dosieron kiel tekstan literal, uzu --str-dosiero/-D.
    Por KaTeX formulo, uzu --katex/-K.
    Por kodbloko kun programlingvo, uzu --str-dosiero/-D kun --kodlingvo/-L,
    aŭ --str -L por unulinia kodaĵeto.
    """
    # Resolve deprecated aliases
    new_subject = resolve_deprecated(nova_subjekto, new_subject,
                                     "new-subject", "nova-subjekto")
    new_predicate = resolve_deprecated(nova_predikato, new_predicate,
                                       "new-predicate", "nova-predikato")
    new_object = resolve_deprecated(nova_objekto, new_object,
                                    "new-object", "nova-objekto")

    # --kodbloko is deprecated: redirect to --str-dosiero with --kodlingvo
    if kodbloko is not None:
        warning(tr_multi(
            "--kodbloko estas malrekomendita, uzu --str-dosiero --kodlingvo <lingvo>",
            "--kodbloko is deprecated, use --str-dosiero --kodlingvo <language>",
            "--kodbloko est déprécié, utilisez --str-dosiero --kodlingvo <langue>",
        ))
        str_dosiero = kodbloko

    # ── Resolve new object source: -K, -D, --nova-objekto ──────────
    new_obj_sourced, katex_flag, kodlingvo_val, str_ = resolve_new_object_source(
        katex, str_dosiero, new_object, kodlingvo, str_,
    )

    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Determine new object type from flags (default URI for backward compat)
    # In modifi mode, --unuo alone keeps the existing arc's type.
    new_datatype, new_object_type = validate_type_flags(
        str_, int_, float_, bool_, lingvo, unuo,
        katex=katex_flag, kodlingvo=kodlingvo_val,
        modifi_mode=True,
    )
    old_object_unit: str | None = None

    # ── Unified partial-match resolution (Issue #97) ──────────────
    # Use resolve_triple() for all paths — it does partial label matching
    # on all three fields, supports "" as wildcard, shows picker for 2+.
    triple = resolve_triple(
        node_svc, pred_svc, triple_svc,
        subject=subject, predicate=predicate, object=object,
    )
    if triple is None:
        raise typer.Exit(1)

    # Extract old values from resolved/picked triple
    subject_uuid = triple["subject_uuid"]
    predicate = triple["predicate_id"]
    object = triple["object_value"]  # noqa: A002
    old_object_type = triple.get("object_type", "uri")
    old_object_lang = triple.get("object_lang")
    old_object_value = triple["object_value"]
    old_object_unit = triple.get("object_unit")
    old_object_datatype = triple.get("object_datatype")

    # ── Handle __KEEP__ sentinel from validate_type_flags ─────────
    # When --unuo is given without a type flag, modifi_mode returns
    # the sentinel.  Check that the existing arc is numeric.
    if new_object_type == "__KEEP__":
        old_dtype = old_object_datatype or ""
        if old_object_type != "literal" or old_dtype not in ("xsd:integer", "xsd:decimal"):
            from A import error as _error
            _error(tr_multi(
                "--unuo bezonas ekzistantan nombran arkon (int/float)",
                "--unuo requires an existing numeric arc (int/float)",
                "--unuo nécessite un arc numérique existant (int/float)",
            ))
            raise typer.Exit(1)
        new_datatype = old_object_datatype
        new_object_type = "literal"

    # ── Resolve new values ────────────────────────────────────────
    # Use resolved UUIDs from the triple dict (not raw CLI args)
    # for the "no change" fallback. Issue #97 unified flow means
    # subject/predicate/object are always resolved values at this point.
    new_subj = new_subject or subject_uuid
    new_pred = new_predicate or predicate
    new_obj_raw = (
        new_obj_sourced if new_obj_sourced is not None
        else new_object if new_object is not None
        else old_object_value
    )

    # Resolve new subject UUID
    new_subj_uuid = resolve_subject_id(node_svc, new_subj, label="nova subjekto")

    # Resolve new object (URI → node lookup, literal → raw value)
    new_obj_value, new_obj_lang = resolve_new_object_value(
        node_svc, new_object_type, new_obj_raw,
        old_object_value, lingvo, str_,
    )

    # ── Resolve unit via UnitService ──────────────────────────────────
    if unuo:
        # Phase 1: Read-only normalization for no-op detection.
        # If the normalized value matches the existing unit, no update
        # is needed and we skip auto-creation entirely.
        effective_unuo = get_unit_service().normalize_unit(unuo)
        if effective_unuo != old_object_unit:
            # Phase 2: Full resolution (may auto-create compound units)
            try:
                effective_unuo = get_unit_service().resolve_unit(unuo)
            except UnitNotFoundError as e:
                error(tr_multi(
                    "Unuo ne trovita: {u}",
                    "Unit not found: {u}",
                    "Unité non trouvée : {u}",
                ).format(u=str(e)))
                raise typer.Exit(1) from e
    else:
        effective_unuo = old_object_unit

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
        and old_object_unit == effective_unuo
    )
    if noop:
        info(tr_multi(
            "Neniu ŝanĝo: arko restas neŝanĝita.",
            "No change: arc remains unchanged.",
            "Aucun changement : l'arc reste inchangé.",
        ))
        return

    # ── Execute: delete old + insert new ──────────────────────────
    execute_modification(
        triple_svc,
        subject_uuid, predicate, old_object_value, old_object_type,
        new_subj_uuid, new_pred, new_object_type, new_obj_value,
        new_obj_lang, new_datatype, effective_unuo,
    )

    # ── Report success ────────────────────────────────────────────
    new_obj_display = format_new_object_display(new_object_type, new_obj_value, new_datatype)
    info(tr_multi(
        "Arko modifita: {s} --{p}--> {o}",
        "Arc modified: {s} --{p}--> {o}",
        "Arc modifié : {s} --{p}--> {o}",
    ).format(s=truncate_uuid(new_subj_uuid), p=new_pred, o=new_obj_display))
