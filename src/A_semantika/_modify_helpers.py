"""Shared helpers for the modifi command.

Extracted from _cli_modify.py for monolith compliance (< 500 lines).
"""
from __future__ import annotations

from pathlib import Path

import typer

from A import error, tr_multi
from A_semantika._cli_helpers import EXT_TO_LANG
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError


# ── Subject ID resolution ──────────────────────────────────────────────


def resolve_subject_id(
    node_svc: "NodeService",
    text: str,
    label: str = "subjekto",
) -> str:
    """Resolve a subject text to a node UUID, or exit on error.

    Args:
        node_svc: NodeService instance.
        text: Subject text (UUID prefix or label).
        label: Context label for error messages (e.g. "nova subjekto").

    Returns:
        Resolved node UUID.

    Raises:
        ``typer.Exit(1)`` via ``error()`` if ambiguous or not found.
    """
    try:
        node = node_svc.resolve_node_id_prefix(text)
    except AmbiguousUUIDError as e:
        error(tr_multi(
            f"Ambigua {label}-prefikso: {{e}}",
            f"Ambiguous {label} prefix: {{e}}",
            f"Préfixe {label} ambigu : {{e}}",
        ).format(e=str(e)))
        raise typer.Exit(1) from e
    if not node:
        error(tr_multi(
            f"{label.capitalize()} ne trovita: {{s}}",
            f"{label.capitalize()} not found: {{s}}",
            f"{label.capitalize()} non trouvé : {{s}}",
        ).format(s=text))
        raise typer.Exit(1)
    return node["node_id"]


# ── New object value resolution ────────────────────────────────────────


def resolve_new_object_value(
    node_svc: "NodeService",
    new_object_type: str,
    new_obj_raw: str | None,
    old_object_value: str,
    lingvo: str | None,
    str_: bool,
) -> tuple[str, str | None]:
    """Resolve the new object value for a modifi operation.

    For URI types, resolves the text to a node UUID.
    For literal types, returns the raw value as-is.

    Args:
        node_svc: NodeService instance.
        new_object_type: Target object type ("uri" or "literal").
        new_obj_raw: Raw new object value from CLI.
        old_object_value: Current object value (fallback if new is None).
        lingvo: Language tag (only for string literals).
        str_: Whether the new object is a string literal.

    Returns:
        Tuple of (resolved_value, object_lang).
    """
    new_obj_value: str = new_obj_raw if new_obj_raw is not None else old_object_value
    new_obj_lang: str | None = lingvo if str_ else None

    if new_object_type == "uri":
        new_obj_raw_clean = new_obj_raw if new_obj_raw is not None else old_object_value
        obj_node = resolve_subject_id(
            node_svc, new_obj_raw_clean, label="nova objekto"
        )
        new_obj_value = obj_node

    return new_obj_value, new_obj_lang


# ── New object source resolution (-K / -D / --nova-objekto) ────────────


def resolve_new_object_source(
    katex: str | None,
    str_dosiero: str | None,
    new_object: str | None,
    kodlingvo: str | None,
    str_: bool,
) -> tuple[str | None, bool, str | None, bool]:
    """Resolve the new object source from mutually exclusive flags.

    Handles --katex/-K, --str-dosiero/-D, and --nova-objekto.
    Returns (new_obj_sourced, katex_flag, kodlingvo_val, str_).

    Calls error() and raises typer.Exit(1) on invalid combinations.
    """
    new_obj_sourced: str | None = None
    katex_flag = False
    kodlingvo_val: str | None = kodlingvo

    # --katex and --str-dosiero are mutually exclusive
    if katex is not None and str_dosiero is not None:
        error(tr_multi(
            "Ne eblas uzi samtempe --katex kaj --str-dosiero",
            "Cannot use --katex and --str-dosiero",
            "Impossible d'utiliser --katex et --str-dosiero",
        ))
        raise typer.Exit(1)

    # --katex and --kodlingvo katex are mutually exclusive
    if katex is not None and kodlingvo_val == "katex":
        error(tr_multi(
            "Ne eblas uzi samtempe --katex kaj --kodlingvo katex",
            "Cannot use both --katex and --kodlingvo katex",
            "Impossible d'utiliser --katex et --kodlingvo katex",
        ))
        raise typer.Exit(1)

    # --katex and --nova-objekto are mutually exclusive
    if katex is not None and new_object is not None:
        error(tr_multi(
            "Ne eblas uzi samtempe --katex kaj --nova-objekto",
            "Cannot use --katex and --nova-objekto",
            "Impossible d'utiliser --katex et --nova-objekto",
        ))
        raise typer.Exit(1)

    # --str-dosiero and --nova-objekto are mutually exclusive
    if str_dosiero is not None and new_object is not None:
        error(tr_multi(
            "Ne eblas uzi samtempe --str-dosiero kaj --nova-objekto",
            "Cannot use --str-dosiero and --nova-objekto",
            "Impossible d'utiliser --str-dosiero et --nova-objekto",
        ))
        raise typer.Exit(1)

    if katex is not None:
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
        new_obj_sourced = formula
        katex_flag = True
        kodlingvo_val = None
    elif str_dosiero is not None:
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
        new_obj_sourced = content
        if kodlingvo_val is None:
            ext = file_path.suffix.lower()
            kodlingvo_val = EXT_TO_LANG.get(ext)

    return new_obj_sourced, katex_flag, kodlingvo_val, str_


# ── Execution ──────────────────────────────────────────────────────────


def execute_modification(
    triple_svc,
    subject_uuid: str,
    predicate: str,
    old_object_value: str,
    old_object_type: str,
    new_subj_uuid: str,
    new_pred: str,
    new_object_type: str,
    new_obj_value: str,
    new_obj_lang: str | None,
    new_datatype: str | None,
    effective_unuo: str | None,
) -> None:
    """Execute a modifi operation: delete old arc + insert new arc.

    Validates the new predicate FK reference before proceeding.
    Calls error() and raises typer.Exit(1) on FK violation or duplicate.
    """
    import sqlite3

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

    from A_semantika.data.storage import now

    timestamp = now()
    try:
        with triple_svc.db.transaction() as conn:
            conn.execute(
                "DELETE FROM triples WHERE subject_uuid=? AND predicate_id=? "
                "AND object_value=? AND object_type=?",
                (subject_uuid, predicate, old_object_value, old_object_type),
            )
            conn.execute(
                """INSERT INTO triples (subject_uuid, predicate_id, object_type,
                                        object_value, object_lang, object_datatype,
                                        object_unit, kreita_je)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_subj_uuid, new_pred, new_object_type, new_obj_value,
                 new_obj_lang, new_datatype, effective_unuo, timestamp),
            )
    except sqlite3.IntegrityError:
        error(tr_multi(
            "Ne eblas modifi: la nova arko jam ekzistas (sama subjekto, predikato, objekto, kaj tipo).",
            "Cannot modify: the new arc already exists (same subject, predicate, object, and type).",
            "Impossible de modifier : le nouvel arc existe déjà (même sujet, prédicat, objet et type).",
        ))
        raise typer.Exit(1)


# ── Display formatting ─────────────────────────────────────────────────


def format_new_object_display(
    new_object_type: str,
    new_obj_value: str,
    new_datatype: str | None,
) -> str:
    """Format the new object value for the success message."""
    if new_object_type == "uri":
        return truncate_uuid(new_obj_value)
    if new_datatype and (new_datatype.startswith("text/") or new_datatype.startswith("application/")):
        return f"{new_datatype}, {len(new_obj_value)} chars"
    return new_obj_value[:80] + "..." if len(new_obj_value) > 80 else new_obj_value
