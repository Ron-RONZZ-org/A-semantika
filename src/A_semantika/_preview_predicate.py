"""Predicate preview table builders and confirmation dialogs.

Extracted from ``_preview.py`` during the 500-line monolith split.
Content columns use ``no_wrap=False`` for text wrapping (#19).
"""

from __future__ import annotations

from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import info, tr_multi
from A.utils.interactive import confirm_action


def build_predicate_preview_table(pred_data: dict) -> Table:
    """Build a preview table showing predicate metadata before creation.

    Args:
        pred_data: Predicate data dict with keys:
            predicate_id, source, etikedoj (dict), priskriboj (dict).

    Returns:
        A Rich Table with predicate details.
    """
    table = Table(show_header=False, box=BOX_SIMPLE)
    table.add_column(tr_multi("Detaloj", "Detail", "Detail"))
    table.add_column("")

    pid = pred_data.get("predicate_id", "")
    table.add_row(tr_multi("ID", "ID", "ID"), pid)

    source = pred_data.get("source", "")
    if source:
        table.add_row(tr_multi("Fonto", "Source", "Source"), source)

    etikedoj = pred_data.get("etikedoj", {})
    if isinstance(etikedoj, dict) and etikedoj:
        labels_str = "\n".join(f"[{lang}] {val}" for lang, val in etikedoj.items())
        table.add_row(tr_multi("Etikedoj", "Labels", "Etiquettes"), labels_str)

    priskriboj = pred_data.get("priskriboj", {})
    if isinstance(priskriboj, dict) and priskriboj:
        descs_str = "\n".join(f"[{lang}] {val}" for lang, val in priskriboj.items())
        table.add_row(tr_multi("Priskriboj", "Descriptions", "Descriptions"), descs_str)

    return table


def build_predicate_modify_preview(
    pred_id: str,
    old_etikedoj: dict[str, str],
    new_etikedoj: dict[str, str] | None,
    old_priskriboj: dict[str, str],
    new_priskriboj: dict[str, str] | None,
    new_predicate_id: str | None = None,
    old_alisoj: list[str] | None = None,
    new_alisoj: list[str] | None = None,
) -> Table | None:
    """Build a preview table showing old -> new values for a predicate modifi.

    Only includes fields that actually changed.  Returns ``None`` if no
    fields changed (no-op).

    Args:
        pred_id: Predicate ID (e.g. ``rdf:type``).
        old_etikedoj: Existing labels dict.
        new_etikedoj: New labels dict, or ``None`` if labels not changing.
        old_priskriboj: Existing descriptions dict.
        new_priskriboj: New descriptions dict, or ``None`` if not changing.
        new_predicate_id: Optional new predicate ID (rename).
        old_alisoj: Existing aliases list, or ``None`` if not applicable.
        new_alisoj: New aliases list, or ``None`` if aliases not changing.

    Returns:
        A Rich Table with old->new columns, or ``None`` if nothing changed.
    """
    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("Kampo", "Field", "Champ"))
    table.add_column(tr_multi("Malnova", "Old", "Ancien"))
    table.add_column(tr_multi("Nova", "New", "Nouveau"))

    has_changes = False

    # Predicate ID rename
    if new_predicate_id is not None and new_predicate_id != pred_id:
        has_changes = True
        table.add_row(
            tr_multi("ID", "ID", "ID"),
            pred_id,
            new_predicate_id,
        )

    # Labels (etikedoj)
    if new_etikedoj is not None and new_etikedoj != old_etikedoj:
        has_changes = True
        old_lines = "\n".join(f"[{k}] {v}" for k, v in sorted(old_etikedoj.items())) if old_etikedoj else "-"
        new_lines = "\n".join(f"[{k}] {v}" for k, v in sorted(new_etikedoj.items())) if new_etikedoj else "-"
        table.add_row(
            tr_multi("Etikedoj", "Labels", "Etiquettes"),
            old_lines,
            new_lines,
        )

    # Descriptions (priskriboj)
    if new_priskriboj is not None and new_priskriboj != old_priskriboj:
        has_changes = True
        old_lines = "\n".join(f"[{k}] {v}" for k, v in sorted(old_priskriboj.items())) if old_priskriboj else "-"
        new_lines = "\n".join(f"[{k}] {v}" for k, v in sorted(new_priskriboj.items())) if new_priskriboj else "-"
        table.add_row(
            tr_multi("Priskriboj", "Descriptions", "Descriptions"),
            old_lines,
            new_lines,
        )

    # Aliases (alisoj)
    if new_alisoj is not None and old_alisoj is not None and new_alisoj != old_alisoj:
        has_changes = True
        old_lines = "\n".join(f"  - {a}" for a in old_alisoj) if old_alisoj else "-"
        new_lines = "\n".join(f"  - {a}" for a in new_alisoj) if new_alisoj else "-"
        table.add_row(
            tr_multi("Alisoj", "Aliases", "Alias"),
            old_lines,
            new_lines,
        )

    return table if has_changes else None


def confirm_predicate_creation(
    pred_data: dict,
    yes: bool = False,
) -> bool:
    """Show a confirmation prompt for creating a predicate.

    Displays a Rich table with predicate details, then asks for confirmation.

    Args:
        pred_data: Predicate data dict.
        yes: If True, skip confirmation.

    Returns:
        True if confirmed, False otherwise.
    """
    if yes:
        return True

    table = build_predicate_preview_table(pred_data)

    info("")
    info(table)

    pid = pred_data.get("predicate_id", "")
    return confirm_action(
        tr_multi(
            f"Cu krei predikaton {pid}?",
            f"Create predicate {pid}?",
            f"Creer le predicat {pid}?",
        ),
        default=True,
    )
