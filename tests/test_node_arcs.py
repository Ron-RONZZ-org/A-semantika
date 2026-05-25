"""Node aldoni with arc shortcuts edge cases.

Extracted from test_edge_cases.py — TestNodeAldoniWithArcs.
"""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


class TestNodeAldoniWithArcs:
    """nodo aldoni with --tipo, --superklaso, --ne, --invers."""

    def test_nodo_aldoni_nonexistent_tipo_warns(self, runner: CliRunner):
        """Using --tipo with a non-existent target should warn, not silently drop."""
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", "eo::TestNode",
            "--tipo", "nonexistent-target",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "ne trovita" in result.stdout or "not found" in result.stdout

    def test_nodo_aldoni_nonexistent_superklaso_warns(self, runner: CliRunner):
        """Using --superklaso with a non-existent target should warn."""
        runner.invoke(app, ["predikato", "aldoni", "rdfs:subClassOf", "-e", "eo::subklaso", "--jes"])
        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", "eo::TestNode2",
            "--superklaso", "nonexistent-target",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "ne trovita" in result.stdout or "not found" in result.stdout

    def test_nodo_aldoni_with_tipo(self, runner: CliRunner):
        """Creating a node with --tipo should add rdf:type arc."""
        target_uuid = "c1000000-0000-0000-0000-000000000001"
        runner.invoke(app, ["nodo", "aldoni", target_uuid, "-e", "eo::Mamulo", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

        # Use explicit UUID prefix
        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", "eo::Hundo",
            "--tipo", target_uuid[:8],
            "--jes",
        ])
        assert result.exit_code == 0
        assert "kreita" in result.stdout or "Created" in result.stdout

    def test_nodo_aldoni_with_superklaso(self, runner: CliRunner):
        """Creating a node with --superklaso should add rdfs:subClassOf arc."""
        target_uuid = "c2000000-0000-0000-0000-000000000002"
        runner.invoke(app, ["nodo", "aldoni", target_uuid, "-e", "eo::Besto", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:subClassOf", "-e", "eo::subklaso", "--jes"])

        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", "eo::Hundo",
            "--superklaso", target_uuid[:8],
            "--jes",
        ])
        assert result.exit_code == 0

    def test_nodo_aldoni_with_ne(self, runner: CliRunner):
        """Creating a node with --ne should add owl:disjointWith arc."""
        target_uuid = "c3000000-0000-0000-0000-000000000003"
        runner.invoke(app, ["nodo", "aldoni", target_uuid, "-e", "eo::Akwah", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "owl:disjointWith", "-e", "eo::malakorda", "--jes"])

        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", "eo::Fajro",
            "--ne", target_uuid[:8],
            "--jes",
        ])
        assert result.exit_code == 0

    def test_nodo_aldoni_with_invers(self, runner: CliRunner):
        """Creating a node with --invers should add owl:inverseOf arc."""
        target_uuid = "c4000000-0000-0000-0000-000000000004"
        runner.invoke(app, ["nodo", "aldoni", target_uuid, "-e", "eo::Antaux", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "owl:inverseOf", "-e", "eo::inversa", "--jes"])

        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", "eo::Malantaux",
            "--invers", target_uuid[:8],
            "--jes",
        ])
        assert result.exit_code == 0
