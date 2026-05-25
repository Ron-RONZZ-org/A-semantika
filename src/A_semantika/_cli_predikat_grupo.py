"""Predikat-grupo subcommand group CLI: ls, vidi, aldoni, modifi, forigi, serci, importi.
"""
from __future__ import annotations

from typing import Any, Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika.data.storage import label_from_json
from A_semantika.service import get_predicate_group_service, get_predicate_service


def _resolve_group_name(group_svc: Any, name: str) -> dict | None:
    """Resolve a group name, supporting prefix matching.

    Tries exact match first, then prefix (LIKE) match.
    If the prefix matches multiple groups, shows an error and raises
    ``typer.Exit(1)``.

    Args:
        group_svc: PredicateGroupService instance.
        name: Group name or prefix.

    Returns:
        The resolved group dict, or None if not found.
    """
    group = group_svc.get_by_field("group_name", name)
    if group:
        return group

    # Prefix match: search for groups where group_name starts with name
    candidates = group_svc.db.execute(
        "SELECT * FROM predicate_groups WHERE group_name LIKE ?",
        (name + "%",),
    )
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Multiple matches — ambiguous
    names = [c["group_name"] for c in candidates]
    error(tr_multi(
        "Grupa nomo '{n}' estas ambigua: {m}",
        "Group name '{n}' is ambiguous: {m}",
        "Nom de groupe '{n}' est ambigu : {m}",
    ).format(n=name, m=", ".join(names)))
    raise typer.Exit(1)

predikat_grupo_app = typer.Typer(
    name="predikat-grupo",
    help=tr_multi(
        "Administri predikat-grupojn",
        "Manage predicate groups",
        "Gérer les groupes de prédicats",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


@predikat_grupo_app.command("ls")
def ls(
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
) -> None:
    """Listi ĉiujn predikat-grupojn."""
    group_svc = get_predicate_group_service()
    groups = group_svc.list(limit=limit)

    if not groups:
        info(tr_multi("Neniuj grupoj.", "No groups.", "Aucun groupe."))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Grupo", "Group", "Groupe"), no_wrap=True)
    table.add_column(tr_multi("Membroj", "Members", "Membres"), no_wrap=True)

    # Single aggregate query to avoid N+1
    group_uuids = [g["uuid"] for g in groups]
    member_counts: dict[str, int] = {}
    if group_uuids:
        placeholders = ",".join("?" * len(group_uuids))
        rows = group_svc.db.execute(
            f"SELECT group_uuid, COUNT(*) AS cnt FROM predicate_group_members "
            f"WHERE group_uuid IN ({placeholders}) GROUP BY group_uuid",
            group_uuids,
        )
        member_counts = {r["group_uuid"]: r["cnt"] for r in rows}

    for g in groups:
        member_count = member_counts.get(g["uuid"], 0)
        table.add_row(g["group_name"], str(member_count))

    info(table)


@predikat_grupo_app.command("vidi")
def vidi(
    group_name: str = typer.Argument(..., help=tr_multi("Grupa nomo", "Group name", "Nom du groupe")),
) -> None:
    """Vidi detalojn de predikat-grupo."""
    group_svc = get_predicate_group_service()
    group = group_svc.get_by_field("group_name", group_name)
    if not group:
        error(tr_multi("Grupo ne trovita: {g}", "Group not found: {g}", "Groupe non trouvé : {g}").format(g=group_name))
        raise typer.Exit(1)

    info(tr_multi(
        "Grupo: {g}", "Group: {g}", "Groupe : {g}",
    ).format(g=group["group_name"]))
    info(tr_multi(
        "UUID: {u}", "UUID: {u}", "UUID : {u}",
    ).format(u=group["uuid"][:8]))

    members = group_svc.list_members(group_name)
    if members:
        info(tr_multi("Membroj:", "Members:", "Membres :"))
        for m in members:
            label = label_from_json(m.get("etikedoj", "{}")) or m["predicate_id"]
            info(f"  - {m['predicate_id']} ({label})")
    else:
        info(tr_multi("Neniuj membroj.", "No members.", "Aucun membre."))

    info(tr_multi("Kreita: {d}", "Created: {d}", "Créé : {d}").format(d=group["kreita_je"]))


@predikat_grupo_app.command("aldoni")
def aldoni(
    group_name: str = typer.Argument(..., help=tr_multi("Grupa nomo", "Group name", "Nom du groupe")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Aldoni novan predikat-grupon."""
    group_svc = get_predicate_group_service()
    existing = group_svc.get_by_field("group_name", group_name)
    if existing:
        error(tr_multi("Grupo jam ekzistas: {g}", "Group already exists: {g}", "Groupe existe déjà : {g}").format(g=group_name))
        raise typer.Exit(1)

    if not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                f"Ĉu krei grupon {group_name}?",
                f"Create group {group_name}?",
                f"Créer le groupe {group_name}?",
            ),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    try:
        group_svc.create({"group_name": group_name})
        info(tr_multi("Grupo kreita: {g}", "Group created: {g}", "Groupe créé : {g}").format(g=group_name))
    except ValueError as e:
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e


@predikat_grupo_app.command("modifi")
def modifi(
    old_name: str = typer.Argument(..., help=tr_multi("Nuna grupa nomo", "Current group name", "Nom actuel du groupe")),
    new_name: str = typer.Argument(..., help=tr_multi("Nova grupa nomo", "New group name", "Nouveau nom du groupe")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Renomi predikat-grupon."""
    group_svc = get_predicate_group_service()

    # Resolve the old group name (supports prefix matching)
    resolved = _resolve_group_name(group_svc, old_name)
    if not resolved:
        error(tr_multi(
            "Grupo ne trovita: {g}",
            "Group not found: {g}",
            "Groupe non trouvé : {g}",
        ).format(g=old_name))
        raise typer.Exit(1)
    resolved_name: str = resolved["group_name"]

    if not yes:
        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                f"Ĉu renomi grupon '{resolved_name}' al '{new_name}'?",
                f"Rename group '{resolved_name}' to '{new_name}'?",
                f"Renommer le groupe '{resolved_name}' en '{new_name}'?",
            ),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    try:
        group_svc.rename(resolved_name, new_name)
        info(tr_multi(
            "Grupo renomita: '{old}' → '{new}'",
            "Group renamed: '{old}' → '{new}'",
            "Groupe renommé : '{old}' → '{new}'",
        ).format(old=old_name, new=new_name))
    except ValueError as e:
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e


@predikat_grupo_app.command("forigi")
def forigi(
    group_names: list[str] = typer.Argument(
        ...,
        help=tr_multi(
            "Grupa nomoj (pluraj)",
            "Group names (multiple)",
            "Noms de groupes (plusieurs)",
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
    """Forigi predikat-grupojn."""
    group_svc = get_predicate_group_service()

    # Phase 1: Resolve all identifiers (with prefix matching)
    resolved: list[dict] = []
    errors: list[tuple[str, str]] = []

    for gname in group_names:
        group = group_svc.get_by_field("group_name", gname)
        if group:
            resolved.append(group)
            continue

        # Prefix match: search for groups where group_name starts with gname
        candidates = group_svc.db.execute(
            "SELECT * FROM predicate_groups WHERE group_name LIKE ?",
            (gname + "%",),
        )
        if not candidates:
            errors.append((gname, tr_multi("ne trovita", "not found", "non trouvé")))
            continue
        if len(candidates) == 1:
            resolved.append(candidates[0])
            continue

        # Ambiguous prefix
        names = [c["group_name"] for c in candidates]
        errors.append((gname, tr_multi(
            "ambigua: {m}",
            "ambiguous: {m}",
            "ambigüe : {m}",
        ).format(m=", ".join(names))))

    # Report resolution errors
    for input_val, reason in errors:
        error(tr_multi(
            "Forigi {i}: {r}", "Delete {i}: {r}", "Supprimer {i} : {r}",
        ).format(i=input_val, r=reason))

    if not resolved:
        error(tr_multi("Nenio forigebla.", "Nothing to delete.", "Rien à supprimer."))
        raise typer.Exit(1)

    # Phase 2: Batch preview and confirmation
    # Single-item deletion skips confirmation (user already specified exact item)
    if not yes and len(resolved) >= 2:
        table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
        table.add_column(tr_multi("Grupo", "Group", "Groupe"), no_wrap=True)
        table.add_column("UUID", no_wrap=True)
        for group in resolved:
            table.add_row(group["group_name"], group["uuid"][:8])
        info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu forigi {n} grupojn?", "Delete {n} groups?", "Supprimer {n} groupes?",
            ).format(n=len(resolved)),
            default=False,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Phase 3: Delete each (clear members first)
    deleted = 0
    for group in resolved:
        try:
            group_svc.clear_members(group["uuid"])
            group_svc.delete(group["uuid"])
            deleted += 1
        except Exception as e:
            error(tr_multi(
                "Eraro forigante {g}: {e}",
                "Error deleting {g}: {e}",
                "Erreur lors de la suppression de {g} : {e}",
            ).format(g=group["group_name"], e=str(e)))

    info(tr_multi(
        "Forigis {d} el {t} grupojn.",
        "Deleted {d} of {t} groups.",
        "Supprimé {d} sur {t} groupes.",
    ).format(d=deleted, t=len(resolved)))


@predikat_grupo_app.command("serci")
def serci(
    query: str = typer.Argument(..., help=tr_multi("Serĉa teksto", "Search text", "Texte de recherche")),
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimume rezultoj", "Max results", "Résultats max")),
) -> None:
    """Serĉi grupojn laŭ nomo."""
    group_svc = get_predicate_group_service()
    pattern = f"%{query}%"
    results = group_svc.db.execute(
        "SELECT * FROM predicate_groups WHERE group_name LIKE ? LIMIT ?",
        (pattern, limit),
    )

    if not results:
        info(tr_multi("Neniuj grupoj trovitaj.", "No groups found.", "Aucun groupe trouvé."))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Grupo", "Group", "Groupe"), no_wrap=True)
    table.add_column(tr_multi("UUID", "UUID", "UUID"), no_wrap=True)

    for g in results:
        table.add_row(g["group_name"], g["uuid"][:8])

    info(table)


@predikat_grupo_app.command("importi")
def importi(
    file: str = typer.Argument(..., help=tr_multi("Dosiero por importi", "File to import", "Fichier à importer")),
) -> None:
    """Importi OWL/RDFS-dosieron (P3: ne disponebla en P1)."""
    info(tr_multi(
        "Importo ne disponebla en P1.",
        "Import not available in P1.",
        "Import non disponible en P1.",
    ))
