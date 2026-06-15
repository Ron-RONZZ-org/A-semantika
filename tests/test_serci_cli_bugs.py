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


class TestSerciDisplayFormat:
    """Tests for serci table display: column headers visible, cell format."""

    @pytest.fixture(autouse=True)
    def _add_long_label(self, node_svc, pred_svc, triple_svc) -> None:
        """Add a node with a long subject label for wrapping tests."""
        node_svc.create({
            "node_id": "LONG_NODE",
            "etikedoj": {"eo": "VeryLongSubjectLabelThatShouldWrapToFitTerminalWidth"},
        })
        triple_svc.add(
            subject_uuid="LONG_NODE", predicate_id="estas_autor_de",
            object_value="DOI_10_1007_BF02", object_type="uri",
        )

    def test_serci_all_column_headers_present(self, runner: CliRunner) -> None:
        """All 4 column headers (Subjekto, Predikato, Objekto, Tipo) appear."""
        result = runner.invoke(app, ["serci"])
        stdout = result.stdout
        assert result.exit_code == 0, f"serci failed: {result.stderr}"
        assert "Subjekto" in stdout or "Subject" in stdout
        assert "Predikato" in stdout or "Predicate" in stdout
        assert "Objekto" in stdout or "Object" in stdout
        assert "Tipo" in stdout or "Type" in stdout

    def test_serci_long_label_visible(self, runner: CliRunner) -> None:
        """Long subject label text appears in output (may wrap across lines)."""
        result = runner.invoke(app, ["serci"])
        assert result.exit_code == 0
        stdout = result.stdout
        # The label wraps mid-word at the column boundary with overflow="fold".
        # Check for the start of the label, which is always contiguous.
        assert "VeryLongSubjectLabel" in stdout

    def test_serci_long_label_node_id_visible(self, runner: CliRunner) -> None:
        """Node ID of long-label subject appears in output (separate line)."""
        result = runner.invoke(app, ["serci"])
        assert result.exit_code == 0
        stdout = result.stdout
        assert "LONG_NODE" in stdout

    def test_serci_count_message_present(self, runner: CliRunner) -> None:
        """Result count message still appears after table."""
        result = runner.invoke(app, ["serci"])
        assert result.exit_code == 0
        stdout = result.stdout
        assert "arkoj trovita" in stdout

    def test_serci_object_label_visible(self, runner: CliRunner) -> None:
        """Object label and ID appear in output."""
        result = runner.invoke(app, ["serci"])
        assert result.exit_code == 0
        stdout = result.stdout
        assert "A Logical Calculus" in stdout
        assert "DOI_10_1007" in stdout
