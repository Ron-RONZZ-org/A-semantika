"""Forigi (delete) triple command.

Extracted from _cli_triples.py to keep each file under 500 lines.
"""
from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr_multi
from A_semantika._triple_picker import pick_triple, pick_triples
from A_semantika._cli_modify_preview import _find_triple_by_spo
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika.service import get_node_service, get_predicate_service, get_provo_service, get_triple_service


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

    # ---- Interactive mode: partial args show picker -------------------
    if predicate is None or object is None:
        triples = pick_triples(
            triple_svc, node_svc, pred_svc,
            subject=subject, predicate=predicate, object=object,
        )
        if triples is None:
            raise typer.Exit(1)

        if not yes:
            from A.utils.interactive import confirm_action

            # Show a compact summary of selected arcs
            info(tr_multi(
                "Elektitaj arkoj ({n}):",
                "Selected arcs ({n}):",
                "Arcs selectionnes ({n}) :",
            ).format(n=len(triples)))
            for t in triples:
                subj_label = resolve_node_label(node_svc, t["subject_uuid"])
                obj_label = (
                    resolve_node_label(node_svc, t["object_value"])
                    if t["object_type"] == "uri"
                    else t["object_value"]
                )
                pred_label = resolve_predicate_label(pred_svc, t["predicate_id"])
                info(f"  {subj_label} --{pred_label}--> {obj_label}")

            if not confirm_action(
                tr_multi(
                    f"Cu forigi {len(triples)} arkojn?",
                    f"Delete {len(triples)} arcs?",
                    f"Supprimer {len(triples)} arcs ?",
                ),
                default=False,
            ):
                info(tr_multi("Nuligita.", "Cancelled.", "Annule."))
                raise typer.Exit(0)

        # Batch delete (cascade proof deletion)
        provo_svc = get_provo_service()
        deleted_count = 0
        for t in triples:
            # Cascade: remove any reified proofs for this arc
            provo_svc.cascade_delete_proofs(
                subject_uuid=t["subject_uuid"],
                predicate_id=t["predicate_id"],
                object_value=t["object_value"],
            )
            deleted = triple_svc.remove(
                subject_uuid=t["subject_uuid"],
                predicate_id=t["predicate_id"],
                object_value=t["object_value"],
                object_type=t.get("object_type", "uri"),
            )
            if deleted:
                deleted_count += 1

        info(tr_multi(
            "Forigis {d} el {n} arkoj.",
            "Deleted {d} of {n} arcs.",
            "Supprime {d} sur {n} arcs.",
        ).format(d=deleted_count, n=len(triples)))
        return

    # ---- Direct mode: full triplet provided (backward compat) --------
    try:
        subj_node = node_svc.resolve_node_id_prefix(subject)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            "Ambigua subjekto-prefikso: {e}",
            "Ambiguous subject prefix: {e}",
            "Prefixe sujet ambigu : {e}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not subj_node:
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
            "Sujet non trouve : {s}",
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
            "Arc non trouve.",
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
                f"Cu forigi arkon: {subj_label} --{predicate}--> {obj_label}?",
                f"Delete arc: {subj_label} --{predicate}--> {obj_label}?",
                f"Supprimer l'arc : {subj_label} --{predicate}--> {obj_label}?",
            ),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annule."))
            raise typer.Exit(0)

    # Cascade: remove any reified proofs for this arc
    provo_svc = get_provo_service()
    provo_svc.cascade_delete_proofs(
        subject_uuid=subject_uuid,
        predicate_id=predicate,
        object_value=obj_value,
    )

    deleted = triple_svc.remove(
        subject_uuid=subject_uuid,
        predicate_id=predicate,
        object_value=obj_value,
        object_type=obj_type,
    )
    if deleted:
        info(tr_multi("Arko forigita.", "Arc deleted.", "Arc supprime."))
    else:
        info(tr_multi("Neniu arko trovita.", "No arc found.", "Aucun arc trouve."))
