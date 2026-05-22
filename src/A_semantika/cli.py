"""A-semantika Typer CLI app.

Entry point registered in pyproject.toml:
    semantika = "A_semantika.cli:app"
"""
from __future__ import annotations

from typing import Optional

import typer

from A import tr_multi

# Root app
app = typer.Typer(
    name="semantika",
    help=tr_multi(
        "Semantika — semantika arko-stokado (RDF-stila triples storo).",
        "Semantika — semantic triple store (RDF-style triple storage).",
        "Semantika — stockage de triplets semantiques (style RDF).",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


# ── Root commands ──────────────────────────────────────────────────────────────


@app.command("aldoni")
def aldoni(
    subject: str = typer.Argument(..., help=tr_multi("Subject UUID", "Subject UUID", "UUID du sujet")),
    predicate: str = typer.Argument(..., help=tr_multi("Predicate ID", "Predicate ID", "ID du predicat")),
    object: str = typer.Argument(..., help=tr_multi("Object value", "Object value", "Valeur de l'objet")),
    uri: bool = typer.Option(False, "-U", "--uri", help=tr_multi("Object estas URI-referenco", "Object is a URI reference", "L'objet est une reference URI")),
    int: bool = typer.Option(False, "--int", help=tr_multi("Entjera literal", "Integer literal", "Litteral entier")),
    float: bool = typer.Option(False, "-f", "--float", help=tr_multi("Float literal", "Float literal", "Litteral flottant")),
    bool: bool = typer.Option(False, "-b", "--bool", help=tr_multi("Buleta literal", "Boolean literal", "Litteral booleen")),
    lingvo: Optional[str] = typer.Option(None, "-l", "--lingvo", help=tr_multi("Lingva etikedo por teksta literal", "Language tag for string literal", "Etiquette de langue pour le litteral textuel")),
    unuo: Optional[str] = typer.Option(None, "-u", "--unuo", help=tr_multi("Unuo UUID por nombraj valoroj", "Unit UUID for numeric values", "UUID d'unite pour les valeurs numeriques")),
    yes: bool = typer.Option(False, "-y", "--yes", help=tr_multi("Preterpasi konfirmon", "Skip confirmation", "Ignorer la confirmation")),
) -> None:
    """Add a semantic triple: subject --predicate--> object."""
    # TODO: implement in P1
    ...


@app.command("modifi")
def modifi(
    triple_ref: str = typer.Argument(..., help=tr_multi("Triple reference (UUID or SPO pattern)", "Triple reference (UUID or SPO pattern)", "Reference du triplet (UUID ou motif SPO)")),
) -> None:
    """Modify an existing triple."""
    ...


@app.command("forigi")
def forigi(
    triple_ref: str = typer.Argument(..., help=tr_multi("Triple reference (UUID or SPO pattern)", "Triple reference (UUID or SPO pattern)", "Reference du triplet (UUID ou motif SPO)")),
) -> None:
    """Delete a triple."""
    ...


@app.command("serci")
def serci(
    subject: Optional[str] = typer.Option(None, "--subject", "-s", help=tr_multi("Subject UUID prefix", "Subject UUID prefix", "Prefixe UUID du sujet")),
    predicate: Optional[str] = typer.Option(None, "--predicate", "-p", help=tr_multi("Predicate ID", "Predicate ID", "ID du predicat")),
    object: Optional[str] = typer.Option(None, "--object", "-o", help=tr_multi("Object value prefix", "Object value prefix", "Prefixe de la valeur de l'objet")),
) -> None:
    """Search triples by subject, predicate, or object."""
    ...


@app.command("vidi")
def vidi(
    subject_uuid: str = typer.Argument(..., help=tr_multi("Subject UUID", "Subject UUID", "UUID du sujet")),
) -> None:
    """Show all triples for a node (subject)."""
    ...


@app.command("eksporti")
def eksporti(
    output: Optional[str] = typer.Option(None, "--output", "-o", help=tr_multi("Output file path (default: stdout)", "Output file path (default: stdout)", "Chemin du fichier de sortie (defaut: stdout)")),
) -> None:
    """Export all triples to Turtle (.ttl) format."""
    ...


# ── Subcommand groups ──────────────────────────────────────────────────────────


# These will be implemented as separate Typer apps in P1:
# nodo_app = typer.Typer(name="nodo", ...)
# predikato_app = typer.Typer(name="predikato", ...)
# predikat_grupo_app = typer.Typer(name="predikat-grupo", ...)
# app.add_typer(nodo_app)
# app.add_typer(predikato_app)
# app.add_typer(predikat_grupo_app)
