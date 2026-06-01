"""Shared rubujo (trash) CLI helpers — parameterized by service type.

Eliminates ~85% code duplication between node and predicate trash CLIs.
Each helper accepts a service getter, ID resolver, and label extractor
to support both ``nodes_rubujo`` and ``predicates_rubujo`` tables.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi, warning
from A_semantika._node_helpers import truncate_uuid
from A_semantika.data.storage import label_from_json


# ── ID Resolution ─────────────────────────────────────────────────────────


def resolve_trash_item(
    db: Any,
    table: str,
    id_column: str,
    item_id: str,
    ambiguous_error: type[Exception],
) -> dict | None:
    """Resolve an item ID prefix against a trash table.

    Tries exact match first (COLLATE NOCASE), then LIKE prefix search
    with wildcard escaping. Raises *ambiguous_error* on multiple matches.

    Args:
        db: SQLiteDB instance.
        table: Trash table name (e.g. ``nodes_rubujo``).
        id_column: ID column name (``node_id`` or ``predicate_id``).
        item_id: User-supplied ID or prefix.
        ambiguous_error: Exception class for ambiguous matches.

    Returns:
        Item dict, or None if not found.
    """
    # Exact match (case-insensitive)
    entry = db.execute_one(
        f"SELECT * FROM {table} WHERE {id_column} = ? COLLATE NOCASE",
        (item_id,),
    )
    if entry:
        return entry

    # Prefix match (LIKE + wildcard escaping)
    escaped = item_id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    entries = db.execute(
        f"SELECT * FROM {table} WHERE {id_column} LIKE ? COLLATE NOCASE ESCAPE '\\'",
        (f"{escaped}%",),
    )
    if not entries:
        return None
    if len(entries) > 1:
        msg = f"ID prefix '{item_id}' is ambiguous ({len(entries)} matches)"
        raise ambiguous_error(msg)
    return entries[0]


def batch_resolve_trash_items(
    db: Any,
    table: str,
    id_column: str,
    item_ids: list[str],
    ambiguous_error: type[Exception],
    *,
    not_found_msg: str = "not found in trash",
    ambiguous_msg: str = "ambiguous prefix: {e}",
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Resolve multiple item ID prefixes against a trash table.

    Returns:
        Tuple of (resolved_items, errors) where errors is
        (input, localized_reason) pairs.
    """
    resolved: list[dict] = []
    errors: list[tuple[str, str]] = []

    for iid in item_ids:
        try:
            item = resolve_trash_item(db, table, id_column, iid, ambiguous_error)
            if item:
                resolved.append(item)
            else:
                errors.append((iid, not_found_msg))
        except ambiguous_error as e:
            errors.append((iid, ambiguous_msg.format(e=str(e))))

    return resolved, errors


# ── Display ────────────────────────────────────────────────────────────────


def get_trash_label(item: dict, id_column: str, label_getter: Callable[[dict], str]) -> str:
    """Get display label for a trash item.

    Tries the label getter first, falls back to the ID.
    """
    label = label_getter(item)
    return label or item.get(id_column, "")


def build_trash_table(
    items: list[dict],
    id_column: str,
    header_id: str,
    header_label: str,
    header_deleted: str,
    label_getter: Callable[[dict], str],
    *,
    show_full_id: bool = False,
) -> Table:
    """Build a Rich table for listing trash items.

    Args:
        items: Trash item dicts.
        id_column: ID column name.
        header_id: Translated column header for ID.
        header_label: Translated column header for label.
        header_deleted: Translated column header for deleted-at.
        label_getter: Function ``(item_dict) -> str``.
        show_full_id: If True, show full ID (no truncation).

    Returns:
        Rich Table instance.
    """
    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(header_id, no_wrap=True)
    table.add_column(header_label, no_wrap=True)
    table.add_column(header_deleted, no_wrap=True)

    # Detect ambiguous short IDs (only for non-predicate tables)
    prefixes: set[str] = set()
    ambiguous: set[str] = set()
    if not show_full_id:
        for n in items:
            nid = n.get(id_column, "?")
            pref = truncate_uuid(nid)
            if pref in prefixes:
                ambiguous.add(pref)
            prefixes.add(pref)

    for n in items:
        label = get_trash_label(n, id_column, label_getter)
        deleted_at = (n.get("forigita_je") or "?")[:19]
        nid = n.get(id_column, "?")
        if show_full_id:
            disp = nid
        elif nid[:16] in ambiguous and len(nid) > 16:
            disp = nid
        else:
            disp = truncate_uuid(nid)
        table.add_row(disp, label, deleted_at)

    return table


def get_label_from_etikedoj(item: dict) -> str:
    """Extract label from etikedoj JSON field."""
    return label_from_json(item.get("etikedoj", "{}"))


# ── Batch restore ──────────────────────────────────────────────────────────


def batch_restore(
    item_ids: list[str],
    service_getter: Callable[[], Any],
    db: Any,
    table: str,
    id_column: str,
    *,
    yes: bool = False,
    entity_name_single: str = "",
    entity_name_plural: str = "",
    label_getter: Callable[[dict], str] | None = None,
) -> None:
    """Batch-restore items from trash.

    Args:
        item_ids: User-supplied ID prefixes.
        service_getter: Callable returning the service instance.
        db: SQLiteDB instance for resolution.
        table: Trash table name.
        id_column: ID column name.
        entity_name_single: Esperanto singular entity name (e.g. ``"nodo"``).
        entity_name_plural: Esperanto plural entity name (e.g. ``"nodoj"``).
        label_getter: Optional label extraction function.
        confirm_label_list: If True, show confirmation for multi-item.
    """
    svc = service_getter()
    label_fn = label_getter or get_label_from_etikedoj

    resolved, errors = batch_resolve_trash_items(
        db, table, id_column, item_ids, ValueError,
        not_found_msg=tr_multi(
            "ne trovita en rubujo",
            "not found in trash",
            "non trouvé dans la corbeille",
        ),
        ambiguous_msg=tr_multi(
            "ambigua prefikso: {e}",
            "ambiguous prefix: {e}",
            "préfixe ambigu : {e}",
        ),
    )

    for input_val, reason in errors:
        error(tr_multi(
            "Restarigi {i}: {r}",
            "Restore {i}: {r}",
            "Restaurer {i} : {r}",
        ).format(i=input_val, r=reason))

    if not resolved:
        error(tr_multi(
            "Nenio restaŭrebla.",
            "Nothing to restore.",
            "Rien à restaurer.",
        ))
        raise typer.Exit(1)

    # Single item: skip confirmation (user already specified exact item)
    if not yes and len(resolved) >= 2:
        label_list = ", ".join(
            get_trash_label(n, id_column, label_fn)
            for n in resolved
        )
        msg = tr_multi(
            f"Ĉu restarigi {len(resolved)} {entity_name_plural}?",
            f"Restore {len(resolved)} {entity_name_plural}?",
            f"Restaurer {len(resolved)} {entity_name_plural}?",
        )
        from A.utils.interactive import confirm_action

        if not confirm_action(msg, default=True):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    restored = 0
    for item in resolved:
        item_id = item[id_column]
        try:
            result = svc.restore(item_id)
            if result:
                restored += 1
                info(tr_multi(
                    "Restarigita: {u}",
                    "Restored: {u}",
                    "Restauré : {u}",
                ).format(u=truncate_uuid(item_id)))
        except (sqlite3.Error, ValueError) as e:
            error(tr_multi(
                "Eraro restarigante {u}: {e}",
                "Error restoring {u}: {e}",
                "Erreur lors de la restauration de {u} : {e}",
            ).format(u=truncate_uuid(item_id), e=str(e)))

    info(tr_multi(
        "Restarigis {r} el {t}.",
        "Restored {r} of {t}.",
        "Restauré {r} sur {t}.",
    ).format(r=restored, t=len(resolved)))


# ── Batch permanent delete ─────────────────────────────────────────────────


def batch_permanent_delete(
    item_ids: list[str],
    service_getter: Callable[[], Any],
    db: Any,
    table: str,
    id_column: str,
    *,
    yes: bool = False,
    label_getter: Callable[[dict], str] | None = None,
) -> None:
    """Permanently delete items from trash.

    Args:
        item_ids: User-supplied ID prefixes.
        service_getter: Callable returning service instance.
        db: SQLiteDB instance.
        table: Trash table name.
        id_column: ID column name.
        label_getter: Optional label extraction function.
    """
    svc = service_getter()
    label_fn = label_getter or get_label_from_etikedoj

    resolved, errors = batch_resolve_trash_items(
        db, table, id_column, item_ids, ValueError,
        not_found_msg=tr_multi(
            "ne trovita en rubujo",
            "not found in trash",
            "non trouvé dans la corbeille",
        ),
        ambiguous_msg=tr_multi(
            "ambigua prefikso: {e}",
            "ambiguous prefix: {e}",
            "préfixe ambigu : {e}",
        ),
    )

    for input_val, reason in errors:
        error(tr_multi(
            "Forigi {i}: {r}",
            "Delete {i}: {r}",
            "Supprimer {i} : {r}",
        ).format(i=input_val, r=reason))

    if not resolved:
        error(tr_multi(
            "Nenio forigebla el rubujo.",
            "Nothing to delete from trash.",
            "Rien à supprimer de la corbeille.",
        ))
        raise typer.Exit(1)

    # Single item: skip confirmation (user already specified exact item)
    if not yes and len(resolved) >= 2:
        table = build_trash_table(
            resolved, id_column,
            tr_multi("ID", "ID", "ID"),
            tr_multi("Etikedo", "Label", "Étiquette"),
            tr_multi("Forigita", "Deleted", "Supprimé"),
            label_fn,
        )
        info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                f"Ĉu permanente forigi {len(resolved)} el la rubujo?",
                f"Permanently delete {len(resolved)} from trash?",
                f"Supprimer définitivement {len(resolved)} de la corbeille?",
            ),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    deleted = 0
    for item in resolved:
        item_id = item[id_column]
        try:
            svc.permanent_delete(item_id)
            deleted += 1
            info(tr_multi(
                "Permanente forigita: {u}",
                "Permanently deleted: {u}",
                "Définitivement supprimé : {u}",
            ).format(u=truncate_uuid(item_id)))
        except (sqlite3.Error, ValueError) as e:
            error(tr_multi(
                "Eraro forigante {u}: {e}",
                "Error deleting {u}: {e}",
                "Erreur lors de la suppression de {u} : {e}",
            ).format(u=truncate_uuid(item_id), e=str(e)))

    info(tr_multi(
        "Permanente forigis {d} el {t}.",
        "Permanently deleted {d} of {t}.",
        "Définitivement supprimé {d} sur {t}.",
    ).format(d=deleted, t=len(resolved)))
