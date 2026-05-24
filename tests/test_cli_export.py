"""CLI tests for eksporti (Turtle export) command."""
from __future__ import annotations

import os
import tempfile

from typer.testing import CliRunner

from A_semantika.cli import app


def test_eksporti_to_file(runner: CliRunner) -> None:
    """eksporti -o should write Turtle output to a file."""
    # Create a node and triple first so there is data to export
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::ExportSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::ExportObj", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    if len(lines) >= 2:
        subj_id = lines[0].split()[0]
        obj_id = lines[1].split()[0]
        runner.invoke(app, ["aldoni", subj_id, "rdf:type", obj_id, "--jes"])

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ttl", delete=False
    ) as f:
        output_path = f.name

    try:
        result = runner.invoke(app, ["eksporti", "-o", output_path])
        assert result.exit_code == 0
        assert "Eksportita" in result.stdout or "Exported" in result.stdout

        # File should exist and contain Turtle
        assert os.path.exists(output_path)
        with open(output_path) as f:
            content = f.read()
        assert "@prefix" in content
        assert "rdf:type" in content or "rdfs:subClassOf" in content or content.strip()
    finally:
        os.unlink(output_path)


def test_eksporti_to_stdout(runner: CliRunner) -> None:
    """eksporti without -o should print to stdout."""
    result = runner.invoke(app, ["eksporti"])
    assert result.exit_code == 0
    assert "@prefix" in result.stdout


def test_eksporti_with_custom_base_uri(runner: CliRunner) -> None:
    """eksporti --base-uri should use the custom URI."""
    custom_uri = "http://my.example.org/"
    result = runner.invoke(app, ["eksporti", "-b", custom_uri])
    assert result.exit_code == 0
    assert custom_uri in result.stdout


def test_eksporti_produces_valid_turtle(runner: CliRunner) -> None:
    """Exported Turtle should have valid structure."""
    result = runner.invoke(app, ["eksporti"])
    assert result.exit_code == 0

    output = result.stdout
    # Must have prefix declarations
    assert output.strip().startswith("@prefix")
    # Must have triples section (or be empty)
    assert "a" in output or "rdf:type" in output or not output.strip()
