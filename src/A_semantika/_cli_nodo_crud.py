"""Nodo CRUD subcommand group: modifi (aldoni extracted to _cli_nodo_aldoni.py)."""
from __future__ import annotations

import json
from typing import Optional

import typer

from A import error, info, tr_multi, warning
from A.utils.interactive import confirm_action
from A_semantika._node_helpers import truncate_uuid
from A_semantika._node_service import AmbiguousUUIDError
from A_semantika._preview import build_node_modify_preview
from A_semantika.service import get_node_service


def _parse_lang_tag_pairs(items: list[str]) -> dict[str, str]:
    """Parse ``LANG::TEKSTO``, ``LANG:TEKSTO``, or plain text list into a dict.

    When a colon separator (``::`` or ``:``) is present, splits into
    language code and text.  When no separator is found, the full text
    is treated as a **language-independent** label (stored with an empty
    string key).

    Strips leading/trailing whitespace from lang and text.
    """
    result: dict[str, str] = {}
    for item in items:
        if "::" in item:
            lang, _, text = item.partition("::")
        elif ":" in item:
            lang, _, text = item.partition(":")
        else:
            # No separator → language-independent label
            text = item.strip()
            if text:
                result[""] = text
            else:
                warning(tr_multi(
                    "Malplena etikedo: {i}",
                    "Empty label: {i}",
                    "Étiquette vide : {i}",
                ).format(i=item))
            continue
        # Strip whitespace from both language code and text
        lang = lang.strip()
        text = text.strip()
        if lang and text:
            result[lang] = text
        else:
            warning(tr_multi(
                "Malplena lingvokodo aŭ teksto en: {i}",
                "Empty language code or text in: {i}",
                "Code de langue ou texte vide dans : {i}",
            ).format(i=item))
    return result


def modifi(
    node_id: str = typer.Argument(..., help=tr_multi("Nod-indekso", "Node ID", "ID du nœud")),
    etikedoj: Optional[list[str]] = typer.Option(None, "-e", "--etikedo", help=tr_multi("Etikedo: LANG::TEKSTO aŭ simple TEKSTO (senlingva)", "Label as LANG::TEXT or plain TEXT (language-independent)", "Étiquette : LANG::TEXTE ou TEXTE simple (indépendant de la langue)")),
    difinoj: Optional[list[str]] = typer.Option(None, "-d", "--difino", help=tr_multi("Difino: LANG::TEKSTO aŭ simple TEKSTO (senlingva)", "Definition as LANG::TEXT or plain TEXT (language-independent)", "Définition : LANG::TEXTE ou TEXTE simple (indépendant de la langue)")),
    nova_id: Optional[str] = typer.Option(None, "--nova-id", "-ni", help=tr_multi("Nova nod-indekso (renomi)", "New node ID (rename)", "Nouvel ID du nœud (renommer)")),
    yes: bool = typer.Option(False, "-y", "--jes", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Modifi nodon."""
    node_svc = get_node_service()
    try:
        node = node_svc.resolve_node_id_prefix(node_id)
    except AmbiguousUUIDError as e:
        error(tr_multi("Ambigua prefikso: {e}", "Ambiguous prefix: {e}", "Préfixe ambigu : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
    if not node:
        # Fallback: substring match
        try:
            node = node_svc.resolve_node_id_substring(node_id)
        except AmbiguousUUIDError as e:
            error(tr_multi("Ambigua nodo: {e}", "Ambiguous node: {e}", "Nœud ambigu : {e}").format(e=str(e)))
            raise typer.Exit(1) from e
    if not node:
        error(tr_multi("Nodo ne trovita: {u}", "Node not found: {u}", "Nœud non trouvé : {u}").format(u=node_id))
        raise typer.Exit(1)

    # Parse existing values
    try:
        old_labels = json.loads(node.get("etikedoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_labels = {}
    try:
        old_defns = json.loads(node.get("difinoj", "{}"))
    except (json.JSONDecodeError, TypeError):
        old_defns = {}

    updates: dict = {}
    new_labels: dict[str, str] | None = None
    new_defns: dict[str, str] | None = None

    if etikedoj:
        parsed_labels = _parse_lang_tag_pairs(etikedoj)
        new_labels = dict(old_labels)
        new_labels.update(parsed_labels)
        updates["etikedoj"] = new_labels

    if difinoj:
        parsed_defns = _parse_lang_tag_pairs(difinoj)
        new_defns = dict(old_defns)
        new_defns.update(parsed_defns)
        updates["difinoj"] = new_defns

    # Handle no-op for --nova-id: same as current ID
    if nova_id and nova_id == node["node_id"]:
        nova_id = None

    if not updates and not nova_id:
        error(tr_multi("Neniu ŝanĝo specifita.", "No changes specified.", "Aucun changement spécifié."))
        raise typer.Exit(1)

    # No-op detection: compare old vs new
    noop = (
        (new_labels is None or new_labels == old_labels)
        and (new_defns is None or new_defns == old_defns)
        and nova_id is None
    )
    if noop:
        info(tr_multi(
            "Neniu ŝanĝo: nodo restas neŝanĝita.",
            "No change: node remains unchanged.",
            "Aucun changement : le nœud reste inchangé.",
        ))
        return

    # Show change summary and confirm
    if not yes:
        table = build_node_modify_preview(
            node["node_id"],
            old_labels, new_labels,
            old_defns, new_defns,
            new_id=nova_id,
        )
        if table:
            info("")
            info(table)

        from A.utils.interactive import confirm_action

        if not confirm_action(
            tr_multi(
                "Ĉu modifi nodon {u}?",
                "Modify node {u}?",
                "Modifier le nœud {u}?",
            ).format(u=truncate_uuid(node["node_id"])),
            default=True,
        ):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    try:
        if nova_id:
            updated = node_svc.update_node_id(node["node_id"], nova_id, updates)
            current_id = updated["node_id"]
            info(tr_multi(
                "Nodo renomita: {old} → {new}",
                "Node renamed: {old} → {new}",
                "Nœud renommé : {old} → {new}",
            ).format(old=truncate_uuid(node["node_id"]), new=truncate_uuid(current_id)))
        else:
            updated = node_svc.update(node["node_id"], updates)
            current_id = updated["node_id"]
            info(tr_multi("Nodo modifita: {u}", "Node modified: {u}", "Nœud modifié : {u}").format(u=truncate_uuid(current_id)))
    except ValueError as e:
        error(tr_multi("Eraro: {e}", "Error: {e}", "Erreur : {e}").format(e=str(e)))
        raise typer.Exit(1) from e
