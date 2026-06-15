"""Shared CLI helpers: interactive picker, type flag validation, predicate
bootstrapping."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService

from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, tr_multi, warning
from A.utils.interactive import select_candidate
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError, NodeService
from A_semantika._preview import resolve_node_label, resolve_predicate_label
from A_semantika._preview_triple import format_tipo
from A_semantika._triple_search import search_triples_by_labels
from A_semantika._triple_service import DuplicateTripleError, TripleService
# Backward-compat re-exports (symbols now live in dedicated modules)
from A_semantika._triple_picker import pick_triple, pick_triples  # noqa: F401
from A_semantika.data.storage import KATEX_DATATYPE


# -- Language-to-MIME mapping for code block literals ------------------

LANG_TO_MIME: dict[str, str] = {
    "python": "text/x-python",
    "javascript": "text/javascript",
    "typescript": "text/typescript",
    "java": "text/x-java",
    "html": "text/html",
    "css": "text/css",
    "bash": "text/x-bash",
    "sh": "text/x-sh",
    "sql": "text/x-sql",
    "yaml": "text/x-yaml",
    "yml": "text/x-yaml",
    "json": "application/json",
    "xml": "application/xml",
    "rust": "text/x-rust",
    "go": "text/x-go",
    "c": "text/x-csrc",
    "cpp": "text/x-c++src",
    "c++": "text/x-c++src",
    "ruby": "text/x-ruby",
    "php": "text/x-php",
    "swift": "text/x-swift",
    "kotlin": "text/x-kotlin",
    "scala": "text/x-scala",
    "r": "text/x-r",
    "lua": "text/x-lua",
    "perl": "text/x-perl",
    "haskell": "text/x-haskell",
    "clojure": "text/x-clojure",
    "elixir": "text/x-elixir",
    "erlang": "text/x-erlang",
    "dart": "text/x-dart",
    "groovy": "text/x-groovy",
    "matlab": "text/x-matlab",
    "diff": "text/x-diff",
    "qd": "text/x-quarkdown",
    "tex": "text/x-tex",
    "latex": "text/x-tex",
    "makefile": "text/x-makefile",
    "dockerfile": "text/x-dockerfile",
    "plain": "text/plain",
    "text": "text/plain",
}

# -- File extension-to-language mapping for code block auto-detection ---
# Maps common file extensions (with leading dot) to LANG_TO_MIME keys.
# Used when --str-dosiero is passed without explicit --kodlingvo.

EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".hs": "haskell",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".edn": "clojure",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".dart": "dart",
    ".groovy": "groovy",
    ".gvy": "groovy",
    ".m": "matlab",
    ".tex": "latex",
    ".sty": "latex",
    ".cls": "latex",
    ".txt": "plain",
    ".md": "plain",
    ".rst": "plain",
    ".diff": "diff",
    ".patch": "diff",
    ".dockerfile": "dockerfile",
    ".makefile": "makefile",
    ".mk": "makefile",
    ".qd": "qd",
}


# ── Ambiguous prefix → interactive selection ──────────────────────────


def _prompt_select_ambiguous_predicate(
    pred_svc: "PredicateService",
    matches: list[dict],
) -> dict | None:
    """Show an interactive numbered picker for ambiguous predicate prefixes.

    Args:
        pred_svc: PredicateService instance.
        matches: List of matching predicate dicts.

    Returns:
        Selected predicate dict, or ``None`` if cancelled.
    """
    from A_semantika._preview import resolve_predicate_label

    result = select_candidate(
        matches,
        columns=[
            {"header": tr_multi("ID", "ID", "ID")},
            {"header": tr_multi("Etikedo", "Label", "Étiquette")},
        ],
        row_formatter=lambda m, i: [
            m["predicate_id"],
            resolve_predicate_label(pred_svc, m["predicate_id"]),
        ],
        prompt_text=tr_multi(
            "Elektu predikaton (aŭ Enter por nuligi)",
            "Select predicate (or Enter to cancel)",
            "Choisissez un prédicat (ou Entrée pour annuler)",
        ),
    )
    if result is None:
        return None
    return result[1]


def _prompt_select_ambiguous_node(
    node_svc: "NodeService",
    matches: list[dict],
) -> dict | None:
    """Show an interactive numbered picker for ambiguous node ID prefixes.

    Args:
        node_svc: NodeService instance.
        matches: List of matching node dicts.

    Returns:
        Selected node dict, or ``None`` if cancelled.
    """
    from A_semantika._preview import resolve_node_label

    result = select_candidate(
        matches,
        columns=[
            {"header": tr_multi("ID", "ID", "ID")},
            {"header": tr_multi("Etikedo", "Label", "Étiquette")},
        ],
        row_formatter=lambda m, i: [
            m["node_id"],
            resolve_node_label(node_svc, m["node_id"]),
        ],
        prompt_text=tr_multi(
            "Elektu nodon (aŭ Enter por nuligi)",
            "Select node (or Enter to cancel)",
            "Choisissez un nœud (ou Entrée pour annuler)",
        ),
    )
    if result is None:
        return None
    return result[1]


# ── Deprecated alias resolution ───────────────────────────────────────


def resolve_deprecated(new_val: object, old_val: object,
                       old_name: str, new_name: str) -> object:
    """Resolve a CLI option renamed from *old_name* to *new_name*.

    If the user passed the old (deprecated) flag, warn and use its value.
    If both old and new are provided, raise an error.
    Returns the value to use (or *new_val* if neither is set).
    """
    if old_val is not None:
        if new_val is not None:
            error(tr_multi(
                f"Ne eblas uzi samtempe --{old_name} kaj --{new_name}",
                f"Cannot use both --{old_name} and --{new_name}",
                f"Impossible d'utiliser --{old_name} et --{new_name} à la fois",
            ))
            raise typer.Exit(1)
        warning(tr_multi(
            f"--{old_name} estas malrekomendita, uzu --{new_name}",
            f"--{old_name} is deprecated, use --{new_name}",
            f"--{old_name} est déprécié, utilisez --{new_name}",
        ))
        return old_val
    return new_val


def count_type_flags(
    str_: bool, int_: bool, float_: bool, bool_: bool,
    katex: bool = False, kodbloko: bool = False,
) -> int:
    """Count how many type flags are set."""
    return sum([str_, int_, float_, bool_, katex, kodbloko])


def validate_type_flags(
    str_: bool, int_: bool, float_: bool, bool_: bool,
    lingvo: str | None, unuo: str | None,
    katex: bool = False, kodbloko: bool = False, kodlingvo: str | None = None,
    modifi_mode: bool = False,
) -> tuple[str | None, str]:
    """Validate type flag combinations.

    Supports plain string (--str), numeric (--int/--float/--bool),
    KaTeX formula (--katex), and code block (--kodbloko) literals.

    When *modifi_mode* is True and only ``--unuo`` is given without a
    type flag, the function returns ``("__KEEP__", "__KEEP__")`` instead
    of raising an error.  The caller should interpret this as "keep the
    existing arc's type unchanged, only update the unit".  The sentinel
    value is a private implementation detail.

    Returns:
        Tuple of (datatype, object_type):
        - datatype: ``None`` for URI/string, ``"xsd:integer"``, etc.
          For KaTeX: returns ``KATEX_DATATYPE`` constant.
          For code block: returns MIME type from ``LANG_TO_MIME`` dict.
        - ``("__KEEP__", "__KEEP__")`` when *modifi_mode* is True and
          only ``--unuo`` is provided.
        - object_type: ``"uri"`` or ``"literal"``

    Calls error() and raises typer.Exit(1) on invalid combinations.
    """
    count = count_type_flags(str_, int_, float_, bool_, katex=katex, kodbloko=kodbloko)
    if count > 1:
        error(
            tr_multi(
                "Ne eblas kombini tipajn flagojn (--str, --int, --float, --bool, --katex, --kodbloko)",
                "Cannot combine type flags (--str, --int, --float, --bool, --katex, --kodbloko)",
                "Impossible de combiner les indicateurs de type (--str, --int, --float, --bool, --katex, --kodbloko)",
            )
        )
        raise typer.Exit(1)

    # kodlingvo requires kodbloko or str (code snippet)
    if kodlingvo and not kodbloko and not str_:
        error(tr_multi(
            "--kodlingvo bezonas --kodbloko aŭ --str",
            "--kodlingvo requires --kodbloko or --str",
            "--kodlingvo nécessite --kodbloko ou --str",
        ))
        raise typer.Exit(1)

    if count == 0:
        if lingvo:
            error(
                tr_multi(
                    "--lingvo bezonas --str aŭ --str-dosiero",
                    "--lingvo requires --str or --str-dosiero",
                    "--lingvo nécessite --str ou --str-dosiero",
                )
            )
            raise typer.Exit(1)
        if unuo:
            if modifi_mode:
                # In modifi mode, --unuo without type flag means "keep
                # existing type". The caller must verify the existing
                # arc is numeric, otherwise this is an error.
                return ("__KEEP__", "__KEEP__")
            error(
                tr_multi(
                    "--unuo bezonas --int aŭ --float",
                    "--unuo requires --int or --float",
                    "--unuo nécessite --int ou --float",
                )
            )
            raise typer.Exit(1)
        return (None, "uri")  # URI reference

    if katex:
        return (KATEX_DATATYPE, "literal")
    if kodbloko:
        mime = LANG_TO_MIME.get(kodlingvo, "text/plain") if kodlingvo else "text/plain"
        return (mime, "literal")
    if str_:
        if kodlingvo:
            if kodlingvo == "katex":
                return (KATEX_DATATYPE, "literal")
            mime = LANG_TO_MIME.get(kodlingvo, "text/plain")
            return (mime, "literal")  # Code snippet
        return (None, "literal")  # Plain string literal
    if int_:
        return ("xsd:integer", "literal")
    if float_:
        return ("xsd:decimal", "literal")
    if bool_:
        return ("xsd:boolean", "literal")
    return (None, "uri")


def ensure_predicate(pred_svc: "PredicateService", predicate_id: str, label_eo: str) -> None:
    """Ensure a predicate exists, creating it if needed.

    Safe for concurrent operations: only ignores duplicate key errors,
    not other errors.
    """
    existing = pred_svc.get_by_predicate_id(predicate_id)
    if existing:
        return
    try:
        pred_svc.create({
            "predicate_id": predicate_id,
            "etikedoj": {"eo": label_eo},
            "source": "rdf",
        })
    except (ValueError, sqlite3.IntegrityError) as e:
        # Only ignore duplicate key errors (race condition from concurrent create)
        err_str = str(e)
        if "UNIQUE constraint failed" not in err_str and "already exists" not in err_str:
            raise


# ── Backward-compat re-exports (deprecated wrappers removed) ──────────
from A_semantika._cli_arc_helpers import (  # noqa: F401
    create_node_arcs,
    resolve_arc_targets,
)
from A_semantika._cli_modify_preview import (  # noqa: F401
    _find_triple_by_spo,
    build_modify_preview,
    find_triple_direct,
)
