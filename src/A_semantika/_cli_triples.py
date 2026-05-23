"""Root triple CLI commands: aldoni, modifi, forigi, serci, vidi, eksporti.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import (
    confirm_triple,
    resolve_node_label,
    resolve_predicate_label,
)
from A_semantika._triple_search import search_triples_by_labels
from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_triple_service,
)

# Root commands are registered directly on the main app in cli.py.
# They are defined here as plain functions (no decorator) to keep
# _cli_triples.py focused and < 500 lines.



def _count_type_flags(str_: bool, int_: bool, float_: bool, bool_: bool) -> int:
    """Count how many type flags are set."""
    return sum([str_, int_, float_, bool_])


def _validate_type_flags(
    str_: bool, int_: bool, float_: bool, bool_: bool, lingvo: str | None, unuo: str | None
) -> str | None:
    """Validate type flag combinations. Returns datatype string or None for URI.

    Raises typer.BadParameter on invalid combinations.
    """
    count = _count_type_flags(str_, int_, float_, bool_)
    if count > 1:
        raise typer.BadParameter(
            tr_multi(
                "Ne eblas kombini --str, --int, --float, --bool",
                "Cannot combine --str, --int, --float, --bool",
                "Impossible de combiner --str, --int, --float, --bool",
            )
        )
    if count == 0:
        # Default: URI reference
        if lingvo:
            from A import warning as _warn

            _warn(
                tr_multi(
                    "--lingvo ignorita sen --str",
                    "--lingvo ignored without --str",
                    "--lingvo ignoré sans --str",
                )
            )
        if unuo:
            from A import warning as _warn

            _warn(
                tr_multi(
                    "--unuo ignorita sen --int aŭ --float",
                    "--unuo ignored without --int or --float",
                    "--unuo ignoré sans --int ou --float",
                )
            )
        return None  # URI reference

    if str_:
        return None  # String literal, no datatype
    if int_:
        return "xsd:integer"
    if float_:
        return "xsd:decimal"
    if bool_:
        return "xsd:boolean"
    return None


# ── Root triple commands ──────────────────────────────────────────────


def aldoni(
    subject: str = typer.Argument(..., help=tr_multi("Subject UUID-prefikso", "Subject UUID prefix", "Préfixe UUID du sujet")),
    predicate: str = typer.Argument(..., help=tr_multi("Predikato ID", "Predicate ID", "ID du prédicat")),
    object: str = typer.Argument(..., help=tr_multi("Objekta valoro", "Object value", "Valeur de l'objet")),  # noqa: A002
    str_: bool = typer.Option(False, "-s", "--str", help=tr_multi(
        "Objekto estas teksta literal (not URI)",
        "Object is a string literal (not URI)",
        "L'objet est un littéral textuel (pas URI)",
    )),
    int_: bool = typer.Option(False, "--int", help=tr_multi(
        "Objekto estas entjera literal (not URI)",
        "Object is an integer literal (not URI)",
        "L'objet est un littéral entier (pas URI)",
    )),
    float_: bool = typer.Option(False, "-f", "--float", help=tr_multi(
        "Objekto estas flosanta literal (not URI)",
        "Object is a float literal (not URI)",
        "L'objet est un littéral flottant (pas URI)",
    )),
    bool_: bool = typer.Option(False, "-b", "--bool", help=tr_multi(
        "Objekto estas bulea literal (not URI)",
        "Object is a boolean literal (not URI)",
        "L'objet est un littéral booléen (pas URI)",
    )),
    lingvo: Optional[str] = typer.Option(None, "-l", "--lingvo", help=tr_multi("Lingva etikedo (nur kun --str)", "Language tag (only with --str)", "Étiquette de langue (seulement avec --str)")),
    unuo: Optional[str] = typer.Option(None, "-u", "--unuo", help=tr_multi("Unuo UUID por nombraj valoroj (nur --int/--float)", "Unit UUID for numeric values (only --int/--float)", "UUID d'unité pour valeurs numériques (seulement --int/--float)")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Aldoni semantikan arkon: subjekto --predikato--> objekto.

    Defaŭlte objekto estas URI referenco (nod UUID). Uzu --str por teksta literal.
    """
    datatype = _validate_type_flags(str_, int_, float_, bool_, lingvo, unuo)
    object_type = "literal" if (str_ or int_ or float_ or bool_) else "uri"

    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Resolve subject UUID
    try:
        subj_node = node_svc.resolve_uuid_prefix(subject)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua subjekto-prefikso: {e}", "Ambiguous subject prefix: {e}", "Préfixe sujet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not subj_node:
        error(tr_multi("Subjekto ne trovita: {s}", "Subject not found: {s}", "Sujet non trouvé : {s}").format(s=subject))
        raise typer.Exit(1)
    subject_uuid = subj_node["uuid"]

    # Resolve object UUID if URI type
    object_uuid = object
    if object_type == "uri":
        try:
            obj_node = node_svc.resolve_uuid_prefix(object)
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua objekto-prefikso: {e}", "Ambiguous object prefix: {e}", "Préfixe objet ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1) from e
        if not obj_node:
            error(tr_multi("Objekto ne trovita: {o}", "Object not found: {o}", "Objet non trouvé : {o}").format(o=object))
            raise typer.Exit(1)
        object_uuid = obj_node["uuid"]

    # Confirm
    if not confirm_triple(
        node_svc, pred_svc,
        subject_uuid, predicate, object_uuid,
        object_type, lingvo, datatype, unuo,
        yes=yes,
    ):
        info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
        raise typer.Exit(0)

    # Validate predicate exists
    if not pred_svc.get_by_predicate_id(predicate):
        error(tr_multi("Predikato ne trovita: {p}", "Predicate not found: {p}", "Prédicat non trouvé : {p}").format(p=predicate))
        raise typer.Exit(1)

    try:
        result = triple_svc.add(
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
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e


def modifi(
    subject: str = typer.Argument(..., help=tr_multi("Nuna subjekto UUID-prefikso", "Current subject UUID prefix", "Préfixe UUID du sujet actuel")),
    predicate: str = typer.Argument(..., help=tr_multi("Nuna predikato ID", "Current predicate ID", "ID du prédicat actuel")),
    object: str = typer.Argument(..., help=tr_multi("Nuna objekta valoro", "Current object value", "Valeur actuelle de l'objet")),  # noqa: A002
    new_subject: Optional[str] = typer.Option(None, "--new-subject", "-ns", help=tr_multi("Nova subjekto UUID-prefikso", "New subject UUID prefix", "Nouveau préfixe UUID du sujet")),
    new_predicate: Optional[str] = typer.Option(None, "--new-predicate", "-np", help=tr_multi("Nova predikato ID", "New predicate ID", "Nouvel ID du prédicat")),
    new_object_val: Optional[str] = typer.Option(None, "--new-object", "-no", help=tr_multi("Nova objekta valoro", "New object value", "Nouvelle valeur de l'objet")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Modifi arkon (forigi + re-aldoni).

    Identigu arkon per nunaj valoroj, specifu novajn valorojn per --new-* flagoj.
    """
    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # Resolve current triple
    try:
        subj_node = node_svc.resolve_uuid_prefix(subject)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua subjekto-prefikso: {e}", "Ambiguous subject prefix: {e}", "Préfixe sujet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not subj_node:
        error(tr_multi("Subjekto ne trovita: {s}", "Subject not found: {s}", "Sujet non trouvé : {s}").format(s=subject))
        raise typer.Exit(1)
    subject_uuid = subj_node["uuid"]

    # Current object is always URI for modifi (compound PK requirement)
    try:
        obj_node = node_svc.resolve_uuid_prefix(object)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua objekto-prefikso: {e}", "Ambiguous object prefix: {e}", "Préfixe objet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not obj_node:
        error(tr_multi("Objekto ne trovita: {o}", "Object not found: {o}", "Objet non trouvé : {o}").format(o=object))
        raise typer.Exit(1)
    object_uuid = obj_node["uuid"]

    existing = triple_svc.get_one(subject_uuid, predicate, object_uuid, "uri")
    if not existing:
        error(tr_multi("Arko ne trovita.", "Arc not found.", "Arc non trouvé."))
        raise typer.Exit(1)

    # Determine new values (keep old if not specified)
    new_subj = new_subject or subject
    new_pred = new_predicate or predicate
    new_obj = new_object_val or object

    # Resolve new values
    try:
        new_subj_node = node_svc.resolve_uuid_prefix(new_subj)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua nova subjekto-prefikso: {e}", "Ambiguous new subject prefix: {e}", "Préfixe nouveau sujet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not new_subj_node:
        error(tr_multi("Nova subjekto ne trovita: {s}", "New subject not found: {s}", "Nouveau sujet non trouvé : {s}").format(s=new_subj))
        raise typer.Exit(1)
    new_subj_uuid = new_subj_node["uuid"]

    try:
        new_obj_node = node_svc.resolve_uuid_prefix(new_obj)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua nova objekto-prefikso: {e}", "Ambiguous new object prefix: {e}", "Préfixe nouvel objet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not new_obj_node:
        error(tr_multi("Nova objekto ne trovita: {o}", "New object not found: {o}", "Nouvel objet non trouvé : {o}").format(o=new_obj))
        raise typer.Exit(1)
    new_obj_uuid = new_obj_node["uuid"]

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
        new_obj_label = resolve_node_label(node_svc, new_obj_val)
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
            "DELETE FROM triples WHERE subject_uuid=? AND predicate_id=? AND object_value=? AND object_type='uri'",
            (subject_uuid, predicate, object_uuid),
        )
        conn.execute(
            """INSERT INTO triples (subject_uuid, predicate_id, object_type, object_value, kreita_je)
               VALUES (?, ?, 'uri', ?, ?)""",
            (new_subj_uuid, new_pred, new_obj_uuid, timestamp),
        )

    info(tr_multi(
        "Arko modifita: {s} --{p}--> {o}",
        "Arc modified: {s} --{p}--> {o}",
        "Arc modifié : {s} --{p}--> {o}",
    ).format(s=new_subj_uuid[:8], p=new_pred, o=new_obj_uuid[:8]))


def forigi(
    subject: str = typer.Argument(..., help=tr_multi("Subjekto UUID-prefikso", "Subject UUID prefix", "Préfixe UUID du sujet")),
    predicate: str = typer.Argument(..., help=tr_multi("Predikato ID", "Predicate ID", "ID du prédicat")),
    object: str = typer.Argument(..., help=tr_multi("Objekta valoro", "Object value", "Valeur de l'objet")),  # noqa: A002
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Forigi semantikan arkon."""
    node_svc = get_node_service()
    triple_svc = get_triple_service()

    try:
        subj_node = node_svc.resolve_uuid_prefix(subject)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua subjekto-prefikso: {e}", "Ambiguous subject prefix: {e}", "Préfixe sujet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not subj_node:
        error(tr_multi("Subjekto ne trovita: {s}", "Subject not found: {s}", "Sujet non trouvé : {s}").format(s=subject))
        raise typer.Exit(1)

    try:
        obj_node = node_svc.resolve_uuid_prefix(object)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua objekto-prefikso: {e}", "Ambiguous object prefix: {e}", "Préfixe objet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not obj_node:
        error(tr_multi("Objekto ne trovita: {o}", "Object not found: {o}", "Objet non trouvé : {o}").format(o=object))
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


def serci(
    subject: Optional[str] = typer.Option(None, "--subject", "-s", help=tr_multi("Subjekto UUID-prefikso aŭ etikedo", "Subject UUID prefix or label", "Préfixe UUID ou étiquette du sujet")),
    predicate: Optional[str] = typer.Option(None, "--predicate", "-p", help=tr_multi("Predikato ID aŭ parta nomo", "Predicate ID or partial name", "ID du prédicat ou nom partiel")),
    object: Optional[str] = typer.Option(None, "--object", "-o", help=tr_multi("Objekto UUID-prefikso, etikedo aŭ valoro", "Object UUID prefix, label or value", "Préfixe UUID objet, étiquette ou valeur")),  # noqa: A002
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
) -> None:
    """Serĉi arkojn laŭ subjekto, predikato aŭ objekto."""
    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    # If any filter is provided, use partial label matching
    if subject or predicate or object:
        results = search_triples_by_labels(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            subject=subject,
            predicate=predicate,
            object=object,
            limit=limit,
        )
    else:
        # No filters: show all triples
        results = triple_svc.db.execute(
            "SELECT * FROM triples ORDER BY subject_uuid LIMIT ?",
            (limit,),
        )

    if not results:
        info(tr_multi("Neniuj arkoj trovitaj.", "No arcs found.", "Aucun arc trouvé."))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Subjekto", "Subject", "Sujet"), no_wrap=True)
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=True)
    table.add_column(tr_multi("Tipo", "Type", "Type"), no_wrap=True)

    for r in results:
        s_label = resolve_node_label(node_svc, r["subject_uuid"])
        p_label = resolve_predicate_label(pred_svc, r["predicate_id"])
        if r["object_type"] == "uri":
            o_label = resolve_node_label(node_svc, r["object_value"])
        else:
            o_label = r["object_value"]
        table.add_row(
            f"{s_label} ({r['subject_uuid'][:8]})",
            p_label,
            o_label,
            r["object_type"],
        )

    info(table)
    info(tr_multi(
        "{n} arkoj trovita(j).",
        "{n} arc(s) found.",
        "{n} arc(s) trouvé(s).",
    ).format(n=len(results)))


def vidi(
    subject_uuid: str = typer.Argument(..., help=tr_multi("Subjekto UUID-prefikso", "Subject UUID prefix", "Préfixe UUID du sujet")),
) -> None:
    """Vidi ĉiujn arkojn por nodo (subjekto)."""
    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    triple_svc = get_triple_service()

    try:
        subj_node = node_svc.resolve_uuid_prefix(subject_uuid)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua subjekto-prefikso: {e}", "Ambiguous subject prefix: {e}", "Préfixe sujet ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not subj_node:
        error(tr_multi("Nodo ne trovita: {s}", "Node not found: {s}", "Nœud non trouvé : {s}").format(s=subject_uuid))
        raise typer.Exit(1)

    subj_label = resolve_node_label(node_svc, subj_node["uuid"])
    from A import info as _info

    _info(tr_multi(
        "Nodo: {label} ({uuid})",
        "Node: {label} ({uuid})",
        "Nœud : {label} ({uuid})",
    ).format(label=subj_label, uuid=subj_node["uuid"][:8]))

    results = triple_svc.get_subject_objects(subj_node["uuid"])
    if not results:
        info(tr_multi("Neniuj arkoj por tiu nodo.", "No arcs for this node.", "Aucun arc pour ce nœud."))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Predikato", "Predicate", "Predicat"), no_wrap=True)
    table.add_column(tr_multi("Objekto", "Object", "Objet"), no_wrap=True)
    table.add_column(tr_multi("Tipo", "Type", "Type"), no_wrap=True)

    for r in results:
        p_label = resolve_predicate_label(pred_svc, r["predicate_id"])
        if r["object_type"] == "uri":
            o_label = resolve_node_label(node_svc, r["object_value"])
        else:
            o_label = r["object_value"]
        table.add_row(p_label, o_label, r["object_type"])

    info(table)


def eksporti(
    output: Optional[str] = typer.Option(None, "--output", "-o", help=tr_multi("Eliga dosiero (defaŭlte: stdout)", "Output file (default: stdout)", "Fichier de sortie (défaut: stdout)")),
    base_uri: str = typer.Option("https://example.org/", "--base-uri", "-b", help=tr_multi("Baza URI por Turtle", "Base URI for Turtle", "URI de base pour Turtle")),
) -> None:
    """Eksporti ĉiujn arkojn al Turtle (.ttl) formato."""
    triple_svc = get_triple_service()

    try:
        ttl = triple_svc.export_turtle(base_uri=base_uri)
    except Exception as e:
        error(tr_multi("Eksporta eraro: {e}", "Export error: {e}", "Erreur d'export : {e}").format(e=str(e)))
        raise typer.Exit(1) from e

    if output:
        try:
            with open(output, "w", encoding="utf-8") as f:
                f.write(ttl)
            info(tr_multi(
                "Eksportita al {path}",
                "Exported to {path}",
                "Exporté vers {path}",
            ).format(path=output))
        except OSError as e:
            error(tr_multi(
                "Ne povis skribi al {path}: {e}",
                "Could not write to {path}: {e}",
                "Impossible d'écrire dans {path} : {e}",
            ).format(path=output, e=str(e)))
            raise typer.Exit(1) from e
    else:
        print(ttl)  # noqa: T201 — intentional stdout output for pipe/redirect
