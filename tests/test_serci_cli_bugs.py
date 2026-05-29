"""Test serci CLI argument parsing and display."""
from __future__ import annotations
import pytest
from typer.testing import CliRunner
from A_semantika.cli import app


@pytest.fixture(autouse=True)
def _setup(node_svc, pred_svc, triple_svc) -> None:
    """Create scenario: triples with DOI as object URI."""
    node_svc.create({"node_id": "H_WMCCULLOCH", "etikedoj": {"eo": "Warren McCulloch"}})
    node_svc.create({"node_id": "H_WPITTS",     "etikedoj": {"eo": "Walter Pitts"}})
    node_svc.create({"node_id": "DOI_10_1007_BF02", "etikedoj": {"eo": "A Logical Calculus"}})
    pred_svc.create({"predicate_id": "estas_autor_de", "etikedoj": {"eo": "estas aŭtoro de"}})
    triple_svc.add(subject_uuid="H_WMCCULLOCH", predicate_id="estas_autor_de",
                   object_value="DOI_10_1007_BF02", object_type="uri")
    triple_svc.add(subject_uuid="H_WPITTS", predicate_id="estas_autor_de",
                   object_value="DOI_10_1007_BF02", object_type="uri")


runner = CliRunner()


class TestSerciCLI:
    def test_serci_positional_finds_triples(self):
        """serci DOI_10_1007_BF02 should find triples via positional arg."""
        result = runner.invoke(app, ["serci", "DOI_10_1007_BF02"])
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        assert result.exit_code == 0
        assert "arkoj trovita" in result.stdout
        # The label "A Logical Calculus" resolves from the node, but Rich may
        # wrap it across lines due to no_wrap=False on the object column.
        assert "2 arkoj" in result.stdout or "2 arkoj" in result.stderr

    def test_serci_objekto_flag_finds_triples(self):
        """serci -o DOI_10_1007_BF02 should find triples."""
        result = runner.invoke(app, ["serci", "--objekto", "DOI_10_1007_BF02"])
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        assert result.exit_code == 0
        assert "arkoj trovita" in result.stdout

    def test_serci_positional_not_given_shows_all(self):
        """serci with no args should show all triples."""
        result = runner.invoke(app, ["serci"])
        print(f"STDOUT: {result.stdout}")
        assert result.exit_code == 0
        assert "arkoj trovita" in result.stdout
