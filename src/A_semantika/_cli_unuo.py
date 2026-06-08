"""CLI subcommand group for unit ontology operations.

Provides ``unuo`` subcommands: ``aldoni``, ``ls``, ``vidi``.
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.box import SIMPLE as BOX_SIMPLE
from rich.table import Table

from A import error, info, tr_multi
from A_semantika._node_helpers import truncate_uuid
from A_semantika._unit_parser import ParseError, parse, to_display_string
from A_semantika._unit_service import UnitNotFoundError
from A_semantika.service import get_unit_service

unuo_app = typer.Typer(
    name="unuo",
    help=tr_multi(
        "Unuoj — unuo-ontologio (SI, kunmetitaj unuoj, esprimoj)",
        "Units — unit ontology (SI, compound units, expressions)",
        "Unités — ontologie des unités (SI, unités composées, expressions)",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


@unuo_app.command("aldoni", help=tr_multi(
    "Aldoni unuon (bazan aŭ esprimon kiel J/K)",
    "Add a unit (base or expression like J/K)",
    "Ajouter une unité (base ou expression comme J/K)",
))
def aldoni(
    esprimo: str = typer.Argument(
        ...,
        metavar="ESPRIMO",
        help=tr_multi(
            "Unuo-esprimo (ekz. J, K, J/K, kg*m/s^2)",
            "Unit expression (e.g. J, K, J/K, kg*m/s^2)",
            "Expression d'unité (ex. J, K, J/K, kg*m/s^2)",
        ),
    ),
    etikedo: Optional[str] = typer.Option(
        None, "-e", "--etikedo",
        help=tr_multi(
            "Etikedo por nova baza unuo (nur sen esprimo)",
            "Label for new base unit (only without expression)",
            "Étiquette pour nouvelle unité de base (seulement sans expression)",
        ),
    ),
    simbolo: Optional[str] = typer.Option(
        None, "-s", "--simbolo",
        help=tr_multi(
            "Simbolo por nova baza unuo",
            "Symbol for new base unit",
            "Symbole pour nouvelle unité de base",
        ),
    ),
) -> None:
    """Aldoni unuon.

    Se *esprimo* estas simpla nomo (ekz. ``J``), ĝi povas esti:
      - Ekzistanta unuo (montras ĝin)
      - Nova baza unuo (se oni donas ``--etikedo``)

    Se *esprimo* enhavas operatorojn (``/``, ``*``, ``^``), ĝi estas
    analizita kiel unuo-esprimo kaj aŭtomate kreas kunmetitajn nodojn.
    """
    svc = get_unit_service()

    # Check if it looks like a simple word or compound expression
    has_operators = any(op in esprimo for op in ("/", "*", "^", "(", ")"))

    if has_operators:
        # Expression mode: parse and auto-create
        if etikedo or simbolo:
            error(tr_multi(
                "--etikedo kaj --simbolo ne validas por esprimoj",
                "--etikedo and --simbolo are not valid for expressions",
                "--etikedo et --simbolo ne sont pas valides pour les expressions",
            ))
            raise typer.Exit(1)
        try:
            ast = parse(esprimo)
            node_id = svc.resolve_unit(esprimo)
            display = to_display_string(ast)
            info(tr_multi(
                "Unuo kreita: {id} ({d})",
                "Unit created: {id} ({d})",
                "Unité créée : {id} ({d})",
            ).format(id=node_id, d=display))
        except (ParseError, UnitNotFoundError, ValueError) as e:
            error(tr_multi(
                "Ne eblas krei unuon: {e}",
                "Cannot create unit: {e}",
                "Impossible de créer l'unité : {e}",
            ).format(e=str(e)))
            raise typer.Exit(1) from e
    else:
        # Simple word mode: resolve or create base unit
        try:
            node_id = svc.resolve_unit(esprimo)
            info(tr_multi(
                "Unuo trovita: {id}",
                "Unit found: {id}",
                "Unité trouvée : {id}",
            ).format(id=node_id))
        except UnitNotFoundError:
            if not etikedo:
                error(tr_multi(
                    "Unuo ne trovita: {e}. Uzu --etikedo por krei novan bazan unuon.",
                    "Unit not found: {e}. Use --etikedo to create a new base unit.",
                    "Unité non trouvée : {e}. Utilisez --etikedo pour créer une nouvelle unité de base.",
                ).format(e=esprimo))
                raise typer.Exit(1)
            label = etikedo
            symbol = simbolo or esprimo
            node_id = svc.create_singleton(esprimo, label=label, symbol=symbol)
            info(tr_multi(
                "Baza unuo kreita: {id} ({s})",
                "Base unit created: {id} ({s})",
                "Unité de base créée : {id} ({s})",
            ).format(id=node_id, s=symbol))


@unuo_app.command("ls", help=tr_multi(
    "Listigi unuojn",
    "List units",
    "Lister les unités",
))
def ls() -> None:
    """List all registered unit nodes with their type and symbol."""
    svc = get_unit_service()
    units = svc.list_units()

    if not units:
        info(tr_multi(
            "Neniuj unuoj.",
            "No units.",
            "Aucune unité.",
        ))
        return

    table = Table(show_header=True, box=BOX_SIMPLE, header_style="bold")
    table.add_column(tr_multi("ID", "ID", "ID"), no_wrap=True)
    table.add_column(tr_multi("Simbolo", "Symbol", "Symbole"), no_wrap=True)
    table.add_column(tr_multi("Tipo", "Type", "Type"), no_wrap=True)
    table.add_column(tr_multi("Etikedo", "Label", "Étiquette"), no_wrap=False)

    for u in units:
        node_id = u.get("node_id", "")
        symbol = u.get("unit_symbol", "")
        unit_type = u.get("unit_type", "")
        # Extract label from etikedoj JSON
        from A_semantika.data.storage import label_from_json

        label = label_from_json(u.get("etikedoj", "{}"))
        table.add_row(truncate_uuid(node_id), symbol, unit_type, label)

    info(table)


@unuo_app.command("vidi", help=tr_multi(
    "Vidi unuon detalojn",
    "View unit details",
    "Voir les détails de l'unité",
))
def vidi(
    ident: str = typer.Argument(
        ...,
        metavar="ID",
        help=tr_multi(
            "Unua ID aŭ esprimo",
            "Unit ID or expression",
            "ID d'unité ou expression",
        ),
    ),
) -> None:
    """Show detailed information about a unit node.

    Includes type, symbol, UCUM code, conversion factors, and
    decomposition (for compound units).
    """
    svc = get_unit_service()

    # Try resolving the input as an expression first
    try:
        node_id = svc.resolve_unit(ident)
    except (UnitNotFoundError, ParseError, ValueError):
        error(tr_multi(
            "Unuo ne trovita: {i}",
            "Unit not found: {i}",
            "Unité non trouvée : {i}",
        ).format(i=ident))
        raise typer.Exit(1)

    unit = svc.get_unit_info(node_id)
    if not unit:
        error(tr_multi(
            "Unuo ne trovita: {i}",
            "Unit not found: {i}",
            "Unité non trouvée : {i}",
        ).format(i=ident))
        raise typer.Exit(1)

    # Display details
    info(tr_multi(
        "=== Unuo: {id} ===",
        "=== Unit: {id} ===",
        "=== Unité : {id} ===",
    ).format(id=node_id))

    if unit.get("symbol"):
        info("  " + tr_multi(
            "Simbolo: {s}",
            "Symbol: {s}",
            "Symbole : {s}",
        ).format(s=unit["symbol"]))

    if unit.get("unit_type"):
        info("  " + tr_multi(
            "Tipo: {t}",
            "Type: {t}",
            "Type : {t}",
        ).format(t=unit["unit_type"]))

    if unit.get("ucum"):
        info("  " + tr_multi(
            "UCUM: {c}",
            "UCUM: {c}",
            "UCUM : {c}",
        ).format(c=unit["ucum"]))

    if unit.get("multiplier"):
        info("  " + tr_multi(
            "Multiplikilo: {m}",
            "Multiplier: {m}",
            "Multiplicateur : {m}",
        ).format(m=unit["multiplier"]))

    if unit.get("offset"):
        info("  " + tr_multi(
            "Ofseto: {o}",
            "Offset: {o}",
            "Décalage : {o}",
        ).format(o=unit["offset"]))

    if unit.get("decomposition"):
        info("  " + tr_multi(
            "Malkompono: {d}",
            "Decomposition: {d}",
            "Décomposition : {d}",
        ).format(d=unit["decomposition"]))

    # Show labels
    from A_semantika.data.storage import label_from_json

    etikedoj = unit.get("etikedoj", "{}")
    label = label_from_json(etikedoj)
    if label:
        info("  " + tr_multi(
            "Etikedo: {l}",
            "Label: {l}",
            "Étiquette : {l}",
        ).format(l=label))
