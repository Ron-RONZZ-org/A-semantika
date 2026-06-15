"""Provo (proof) CLI subcommand group.

Commands:
  aldoni  — Attach a reified proof to an arc
  vidi    — View proof(s) attached to an arc (delegates to nodo vidi)
  forigi  — Remove a proof from an arc
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from A import error, info, tr_multi
from A_semantika._cli_helpers import pick_triple
from A_semantika._node_helpers import truncate_uuid
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika._preview_provo import build_proof_confirm_table, build_proof_list_table
from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_provo_service,
    get_triple_service,
)

provo_app = typer.Typer(
    name="provo",
    help=tr_multi(
        "Pruvoj — administri reigitajn pruvojn por arkoj",
        "Proofs — manage reified proofs for arcs",
        "Preuves — gérer les preuves réifiées pour les arcs",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


# ── Shared helpers ──────────────────────────────────────────────────


def _resolve_triple_for_provo(
    subject: str | None,
    predicate: str | None,
    object: str | None,  # noqa: A002
) -> dict | None:
    """Resolve a triple by partial args, showing interactive picker if needed.

    Returns the resolved triple dict or None if cancelled/not found.
    """
    triple_svc = get_triple_service()
    node_svc = get_node_service()
    pred_svc = get_predicate_service()

    if predicate is None or object is None:
        # Interactive picker
        return pick_triple(
            triple_svc, node_svc, pred_svc,
            subject=subject, predicate=predicate, object=object,
        )

    # Direct mode: all three args provided, resolve them
    from A_semantika._node_service import AmbiguousUUIDError
    from A_semantika._predicate_service import AmbiguousPredicateError
    from A_semantika._cli_modify_preview import find_triple_direct

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
        ))
        raise typer.Exit(1)
    subject_uuid = subj_node["node_id"]

    # Resolve predicate prefix
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
        ))
        raise typer.Exit(1)
    predicate_id = pred["predicate_id"]

    # Find the target triple (URI first, then literal fallback)
    triple, _obj_type, _obj_lang = find_triple_direct(
        triple_svc, node_svc, subject_uuid, predicate_id, object,
    )
    if not triple:
        error(tr_multi(
            "Arko ne trovita.",
            "Arc not found.",
            "Arc non trouvé.",
        ))
        raise typer.Exit(1)

    return triple


def _read_proof_file(path_str: str) -> str:
    """Read proof text from a file path (UTF-8).

    Raises:
        typer.Exit(1) on error with user-friendly message.
    """
    file_path = Path(path_str)
    try:
        return file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        error(tr_multi(
            "Dosiero ne trovita: {f}",
            "File not found: {f}",
            "Fichier non trouvé : {f}",
        ).format(f=path_str))
        raise typer.Exit(1) from None
    except IsADirectoryError:
        error(tr_multi(
            "{f} estas dosierujo, ne dosiero",
            "{f} is a directory, not a file",
            "{f} est un dossier, pas un fichier",
        ).format(f=path_str))
        raise typer.Exit(1) from None
    except UnicodeDecodeError:
        error(tr_multi(
            "{f} ne estas valida UTF-8 dosiero",
            "{f} is not a valid UTF-8 file",
            "{f} n'est pas un fichier UTF-8 valide",
        ).format(f=path_str))
        raise typer.Exit(1) from None


# ── aldoni ──────────────────────────────────────────────────────────


@provo_app.command("aldoni", help=tr_multi(
    "Aldoni reigitan pruvon al arko",
    "Add a reified proof to an arc",
    "Ajouter une preuve réifiée à un arc",
))
def provo_aldoni(
    subject: Optional[str] = typer.Argument(
        None,
        metavar="SUBJEKTO",
        help=tr_multi(
            "Subjekto UUID-prefikso aŭ etikedo (malplena = elekti)",
            "Subject UUID prefix or label (empty = pick)",
            "Préfixe UUID ou étiquette du sujet (vide = choisir)",
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
    dosiero: str = typer.Option(
        ...,
        "--str-dosiero", "-D",
        help=tr_multi(
            "Pruvo-dosiero (UTF-8 markdown)",
            "Proof file (UTF-8 markdown)",
            "Fichier de preuve (markdown UTF-8)",
        ),
    ),
    lingvo: Optional[str] = typer.Option(
        None, "-l", "--lingvo",
        help=tr_multi(
            "Lingva etikedo (ekz. eo, en)",
            "Language tag (e.g. eo, en)",
            "Étiquette de langue (ex. eo, en)",
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
    """Aldoni reigitan pruvon al ekzistanta arko.

    SUBJEKTO, PREDIKATO, OBJEKTO estas maldevigaj:
    se oni ne donas ilin, aperas interaktiva listo por elekti la arkon.

    -D/--str-dosiero estas deviga: legu pruvan tekston el UTF-8 dosiero.
    """
    # Resolve the target triple
    triple = _resolve_triple_for_provo(subject, predicate, object)
    if triple is None:
        raise typer.Exit(1)

    subject_uuid = triple["subject_uuid"]
    predicate_id = triple["predicate_id"]
    obj_value = triple["object_value"]
    obj_type = triple.get("object_type", "uri")
    obj_lang = triple.get("object_lang")

    # Read proof text from file
    proof_text = _read_proof_file(dosiero)
    if not proof_text.strip():
        error(tr_multi(
            "Pruvo-dosiero estas malplena.",
            "Proof file is empty.",
            "Le fichier de preuve est vide.",
        ))
        raise typer.Exit(1)

    node_svc = get_node_service()
    pred_svc = get_predicate_service()
    provo_svc = get_provo_service()

    # Check if a proof already exists
    existing_stmt = provo_svc._find_reification_node(
        subject_uuid, predicate_id, obj_value,
    )

    # Show preview
    if not yes:
        subj_label = resolve_node_label(node_svc, subject_uuid)
        pred_label = resolve_predicate_label(pred_svc, predicate_id)
        if obj_type == "uri":
            obj_label = resolve_node_label(node_svc, obj_value)
        else:
            obj_label = obj_value

        table, footnote = build_proof_confirm_table(
            subj_label, subject_uuid,
            pred_label, predicate_id,
            obj_label, obj_value,
            obj_type, proof_text,
            is_update=(existing_stmt is not None),
        )
        info("")
        info(table)
        info(footnote)

        from A.utils.interactive import confirm_action
        if not confirm_action(
            tr_multi(
                "Ĉu aldoni pruvon al tiu arko?",
                "Add proof to this arc?",
                "Ajouter une preuve à cet arc ?",
            ),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Create/replace proof
    result = provo_svc.create_proof(
        subject_uuid=subject_uuid,
        predicate_id=predicate_id,
        object_value=obj_value,
        object_type=obj_type,
        proof_text=proof_text,
        lingvo=lingvo,
    )

    if result["created"]:
        info(tr_multi(
            "Pruvo kreita: {id}",
            "Proof created: {id}",
            "Preuve créée : {id}",
        ).format(id=result["stmt_node_id"]))
    else:
        info(tr_multi(
            "Pruvo ĝisdatigita: {id}",
            "Proof updated: {id}",
            "Preuve mise à jour : {id}",
        ).format(id=result["stmt_node_id"]))


# ── vidi ────────────────────────────────────────────────────────────


@provo_app.command("vidi", help=tr_multi(
    "Vidi pruvon de arko (delegas al nodo vidi)",
    "View proof of an arc (delegates to node vidi)",
    "Voir la preuve d'un arc (délègue à nœud vidi)",
))
def provo_vidi(
    subject: Optional[str] = typer.Argument(
        None,
        metavar="SUBJEKTO",
        help=tr_multi(
            "Subjekto UUID-prefikso aŭ etikedo, aŭ pruva nodo ID",
            "Subject UUID prefix or label, or proof node ID",
            "Préfixe UUID du sujet ou étiquette, ou ID nœud de preuve",
        ),
    ),
    predicate: Optional[str] = typer.Argument(
        None,
        metavar="PREDIKATO",
        help=tr_multi(
            "Predikato ID aŭ parta nomo (preterlasu por vidi pruvan nodon rekte)",
            "Predicate ID or partial name (omit to view proof node directly)",
            "ID du prédicat ou nom partiel (omettre pour voir le nœud de preuve directement)",
        ),
    ),
    object: Optional[str] = typer.Argument(  # noqa: A002
        None,
        metavar="OBJEKTO",
        help=tr_multi(
            "Objekta valoro (preterlasu por vidi pruvan nodon rekte)",
            "Object value (omit to view proof node directly)",
            "Valeur de l'objet (omettre pour voir le nœud de preuve directement)",
        ),
    ),
) -> None:
    """Vidi pruvon.

    Se oni donas nur SUBJEKTO, ĝi traktiĝas kiel pruva noda ID
    kaj vokas ``nodo vidi`` sub la fono.

    Se oni donas SUBJEKTO PREDIKATO OBJEKTO, ĝi serĉas pruvojn
    por tiu arko kaj montras ilin.
    """
    node_svc = get_node_service()

    # Single arg: treat as proof node ID → delegate to nodo vidi
    if predicate is None and object is None and subject is not None:
        # Check if this looks like a proof node (starts with PROVO_)
        # or just delegate directly
        node = node_svc.resolve_node_id_prefix(subject)
        if not node:
            try:
                node = node_svc.resolve_node_id_substring(subject)
            except Exception:
                pass
        if not node:
            error(tr_multi(
                "Nodo ne trovita: {s}",
                "Node not found: {s}",
                "Nœud non trouvé : {s}",
            ))
            raise typer.Exit(1)

        # Delegate to nodo vidi by calling the underlying function directly
        from A_semantika._cli_nodo import vidi as _nodo_vidi
        _nodo_vidi(node_id=subject)
        return

    # Three args: find proofs for the arc
    triple = _resolve_triple_for_provo(subject, predicate, object)
    if triple is None:
        raise typer.Exit(1)

    provo_svc = get_provo_service()
    pred_svc = get_predicate_service()

    proofs = provo_svc.find_proofs(
        triple["subject_uuid"],
        triple["predicate_id"],
        triple["object_value"],
    )

    if not proofs:
        info(tr_multi(
            "Neniuj pruvoj por tiu arko.",
            "No proofs for this arc.",
            "Aucune preuve pour cet arc.",
        ))
        return

    # Show proof list
    s_label = resolve_node_label(node_svc, triple["subject_uuid"])
    p_label = resolve_predicate_label(pred_svc, triple["predicate_id"])
    o_label = (
        resolve_node_label(node_svc, triple["object_value"])
        if triple.get("object_type") == "uri"
        else triple["object_value"]
    )

    info(tr_multi(
        "Pruvoj por {s} --{p}--> {o} ({n} trovita(j)):",
        "Proofs for {s} --{p}--> {o} ({n} found):",
        "Preuves pour {s} --{p}--> {o} ({n} trouvée(s)) :",
    ).format(s=s_label, p=p_label, o=o_label, n=len(proofs)))

    table = build_proof_list_table(proofs)
    if table:
        info("")
        info(table)

    info(tr_multi(
        "Uzu 'nodo vidi <pruva_nodo_id>' por vidi plenan enhavon.",
        "Use 'node vidi <proof_node_id>' to see full content.",
        "Utilisez 'nodo vidi <id_nœud_preuve>' pour voir le contenu complet.",
    ))


# ── forigi ──────────────────────────────────────────────────────────


@provo_app.command("forigi", help=tr_multi(
    "Forigi pruvon de arko",
    "Remove a proof from an arc",
    "Supprimer une preuve d'un arc",
))
def provo_forigi(
    subject: Optional[str] = typer.Argument(
        None,
        metavar="SUBJEKTO",
        help=tr_multi(
            "Subjekto UUID-prefikso aŭ pruva nodo ID",
            "Subject UUID prefix or proof node ID",
            "Préfixe UUID du sujet ou ID du nœud de preuve",
        ),
    ),
    predicate: Optional[str] = typer.Argument(
        None,
        metavar="PREDIKATO",
        help=tr_multi(
            "Predikato ID (preterlasu por forigi pruvan nodon rekte)",
            "Predicate ID (omit to delete proof node directly)",
            "ID du prédicat (omettre pour supprimer le nœud de preuve directement)",
        ),
    ),
    object: Optional[str] = typer.Argument(  # noqa: A002
        None,
        metavar="OBJEKTO",
        help=tr_multi(
            "Objekta valoro (preterlasu por forigi pruvan nodon rekte)",
            "Object value (omit to delete proof node directly)",
            "Valeur de l'objet (omettre pour supprimer le nœud de preuve directement)",
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
    """Forigi pruvon.

    Se oni donas nur SUBJEKTO, ĝi traktiĝas kiel pruva noda ID
    kaj forigas tiun pruvon rekte.

    Se oni donas SUBJEKTO PREDIKATO OBJEKTO, ĝi listigas ĉiujn
    pruvojn por tiu arko kaj permesas elekti kiun forigi.
    """
    node_svc = get_node_service()
    provo_svc = get_provo_service()

    # Single arg: delete proof node directly
    if predicate is None and object is None and subject is not None:
        # Check if node exists
        node = node_svc.get(subject)
        if not node:
            # Try prefix resolution
            try:
                resolved = node_svc.resolve_node_id_prefix(subject)
            except Exception:
                resolved = None
            if not resolved:
                try:
                    resolved = node_svc.resolve_node_id_substring(subject)
                except Exception:
                    pass
            if not resolved:
                error(tr_multi(
                    "Pruva nodo ne trovita: {s}",
                    "Proof node not found: {s}",
                    "Nœud de preuve non trouvé : {s}",
                ))
                raise typer.Exit(1)
            subject = resolved["node_id"]

        # Show preview
        if not yes:
            from A.utils.interactive import confirm_action
            if not confirm_action(
                tr_multi(
                    f"Ĉu forigi pruvan nodon {truncate_uuid(subject)}?",
                    f"Delete proof node {truncate_uuid(subject)}?",
                    f"Supprimer le nœud de preuve {truncate_uuid(subject)} ?",
                ),
                default=False,
            ):
                info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
                raise typer.Exit(0)

        deleted = provo_svc.delete_proof(subject)
        if deleted:
            info(tr_multi(
                "Pruvo forigita: {id}",
                "Proof deleted: {id}",
                "Preuve supprimée : {id}",
            ).format(id=truncate_uuid(subject)))
        else:
            info(tr_multi(
                "Pruvo ne trovita: {id}",
                "Proof not found: {id}",
                "Preuve non trouvée : {id}",
            ))
        return

    # Three args: find proofs for the arc, let user pick
    triple = _resolve_triple_for_provo(subject, predicate, object)
    if triple is None:
        raise typer.Exit(1)

    pred_svc = get_predicate_service()
    proofs = provo_svc.find_proofs(
        triple["subject_uuid"],
        triple["predicate_id"],
        triple["object_value"],
    )

    if not proofs:
        info(tr_multi(
            "Neniuj pruvoj por tiu arko.",
            "No proofs for this arc.",
            "Aucune preuve pour cet arc.",
        ))
        return

    if len(proofs) == 1:
        # Single proof — delete directly
        stmt_id = proofs[0]["stmt_node_id"]
        s_label = resolve_node_label(node_svc, triple["subject_uuid"])
        p_label = resolve_predicate_label(pred_svc, triple["predicate_id"])
        o_label = (
            resolve_node_label(node_svc, triple["object_value"])
            if triple.get("object_type") == "uri"
            else triple["object_value"]
        )

        if not yes:
            from A.utils.interactive import confirm_action
            if not confirm_action(
                tr_multi(
                    f"Ĉu forigi pruvon por {s_label} --{p_label}--> {o_label}?",
                    f"Delete proof for {s_label} --{p_label}--> {o_label}?",
                    f"Supprimer la preuve pour {s_label} --{p_label}--> {o_label} ?",
                ),
                default=False,
            ):
                info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
                raise typer.Exit(0)

        provo_svc.delete_proof(stmt_id)
        info(tr_multi(
            "Pruvo forigita: {id}",
            "Proof deleted: {id}",
            "Preuve supprimée : {id}",
        ).format(id=truncate_uuid(stmt_id)))
    else:
        # Multiple proofs — show list and let user pick
        s_label = resolve_node_label(node_svc, triple["subject_uuid"])
        p_label = resolve_predicate_label(pred_svc, triple["predicate_id"])
        o_label = (
            resolve_node_label(node_svc, triple["object_value"])
            if triple.get("object_type") == "uri"
            else triple["object_value"]
        )

        info(tr_multi(
            "Pruvoj por {s} --{p}--> {o}:",
            "Proofs for {s} --{p}--> {o}:",
            "Preuves pour {s} --{p}--> {o} :",
        ).format(s=s_label, p=p_label, o=o_label))

        from A.utils.interactive import select_candidate
        result = select_candidate(
            proofs,
            columns=[
                {"header": tr_multi("N-ro", "#", "N°")},
                {"header": tr_multi("Pruva Nodo", "Proof Node", "Nœud Preuve")},
                {"header": tr_multi("Antaŭrigardo", "Preview", "Aperçu")},
            ],
            row_formatter=lambda p, i: [
                str(i),
                truncate_uuid(p["stmt_node_id"]),
                (p.get("proof_text") or "")[:50],
            ],
            prompt_text=tr_multi(
                "Elektu pruvon por forigi (aŭ Enter por nuligi)",
                "Select proof to delete (or Enter to cancel)",
                "Choisissez la preuve à supprimer (ou Entrée pour annuler)",
            ),
        )
        if result is None:
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

        stmt_id = result[1]["stmt_node_id"]
        if not yes:
            from A.utils.interactive import confirm_action
            if not confirm_action(
                tr_multi(
                    f"Ĉu forigi pruvan nodon {truncate_uuid(stmt_id)}?",
                    f"Delete proof node {truncate_uuid(stmt_id)}?",
                    f"Supprimer le nœud de preuve {truncate_uuid(stmt_id)} ?",
                ),
                default=False,
            ):
                info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
                raise typer.Exit(0)

        provo_svc.delete_proof(stmt_id)
        info(tr_multi(
            "Pruvo forigita: {id}",
            "Proof deleted: {id}",
            "Preuve supprimée : {id}",
        ).format(id=truncate_uuid(stmt_id)))
