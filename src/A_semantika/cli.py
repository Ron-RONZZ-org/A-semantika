"""A-semantika Typer CLI — thin entry point wiring commands and sub-typers.

Registered as entry point in pyproject.toml:
    semantika = "A_semantika.cli:app"
"""
from __future__ import annotations

import typer

from A import tr_multi
from A_semantika._cli_nodo import nodo_app
from A_semantika._cli_predikat_grupo import predikat_grupo_app
from A_semantika._cli_predikato import predikato_app
from A_semantika._cli_predikato_rubujo import predikato_rubujo_app
from A_semantika._cli_rubujo import rubujo_app

# Root triple commands (defined in _cli_*.py files)
from A_semantika._cli_modify import modifi
from A_semantika._cli_query import eksporti, serci, vidi
from A_semantika._cli_triples import aldoni, forigi

app = typer.Typer(
    name="semantika",
    help=tr_multi(
        "Semantika — semantika arko-stokado (RDF-stila triples storo).",
        "Semantika — semantic triple store (RDF-style triple storage).",
        "Semantika — stockage de triplets sémantiques (style RDF).",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

# ── Root commands ──────────────────────────────────────────────────

app.command(name="aldoni")(aldoni)
app.command(name="modifi")(modifi)
app.command(name="forigi")(forigi)
app.command(name="serci")(serci)
app.command(name="vidi")(vidi)
app.command(name="eksporti")(eksporti)

# ── Subcommand groups ──────────────────────────────────────────────

app.add_typer(nodo_app)
app.add_typer(predikato_app)
predikato_app.add_typer(predikato_rubujo_app)
app.add_typer(predikat_grupo_app)
app.add_typer(rubujo_app)
