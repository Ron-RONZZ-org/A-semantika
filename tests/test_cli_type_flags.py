"""B3: validate_type_flags exit path tests."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app


def test_aldoni_lingvo_without_str_exits_error(runner: CliRunner) -> None:
    """--lingvo without --str should exit with error (B3)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::B3Subj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    if not lines:
        pytest.skip("No nodes available")
    subj_id = lines[0].split()[0]

    # Try aldoni with --lingvo but no --str — should error, not just warn
    result = runner.invoke(app, [
        "aldoni", subj_id, "rdf:type", "Hundo", "--lingvo", "eo", "--jes",
    ])
    assert result.exit_code == 1
    assert "bezonas" in result.stdout or "requires" in result.stdout


def test_aldoni_unuo_without_int_or_float_exits_error(runner: CliRunner) -> None:
    """--unuo without --int or --float should exit with error (B3)."""
    runner.invoke(app, ["nodo", "aldoni", "-e", "eo::B3UnuoSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
    ls_result = runner.invoke(app, ["nodo", "ls"])
    lines = [l for l in ls_result.stdout.strip().split("\n") if l and l[0].isalnum()]
    if not lines:
        pytest.skip("No nodes available")
    subj_id = lines[0].split()[0]

    # Try aldoni with --unuo but no --int or --float — should error
    result = runner.invoke(app, [
        "aldoni", subj_id, "rdf:type", "Hundo", "--unuo", "abc123", "--jes",
    ])
    assert result.exit_code == 1
    assert "bezonas" in result.stdout or "requires" in result.stdout


def test_aldoni_str_with_kodlingvo_creates_code_snippet(runner: CliRunner) -> None:
    """--str with --kodlingvo should create a code snippet (not plain string)."""
    runner.invoke(app, ["nodo", "aldoni", "B3KodSubj", "-e", "eo::B3KodSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    result = runner.invoke(app, [
        "aldoni", "B3KodSubj", "rdf:type", "--str", "print('hello')", "--kodlingvo", "python", "--jes",
    ])
    assert result.exit_code == 0, f"--str --kodlingvo failed: {result.stdout}"
    assert "kreita" in result.stdout or "created" in result.stdout or "Arc" in result.stdout


def test_aldoni_kodlingvo_without_kodbloko_and_without_str_exits_error(runner: CliRunner) -> None:
    """--kodlingvo without --kodbloko and without --str should exit with error."""
    runner.invoke(app, ["nodo", "aldoni", "B3KodSubj2", "-e", "eo::B3KodSubj2", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    # No --str, no --kodbloko — just a positional URI object with --kodlingvo
    result = runner.invoke(app, [
        "aldoni", "B3KodSubj2", "rdf:type", "Hundo", "--kodlingvo", "python", "--jes",
    ])
    assert result.exit_code == 1
    assert "bezonas" in result.stdout or "requires" in result.stdout


# ── -L katex special case ─────────────────────────────────────────────


def test_aldoni_kodlingvo_katex_with_str_sets_katex_datatype(runner: CliRunner) -> None:
    """--str -L katex should set KATEX_DATATYPE in object_datatype."""
    runner.invoke(app, ["nodo", "aldoni", "Ktx1", "-e", "eo::Ktx1", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    result = runner.invoke(app, [
        "aldoni", "Ktx1", "rdf:type", "--str", "E=mc^2", "-L", "katex", "--jes",
    ])
    assert result.exit_code == 0, f"--str -L katex failed: {result.stdout}"
    assert "kreita" in result.stdout.lower()


def test_aldoni_kodlingvo_katex_mutual_exclusion_with_katex_flag(runner: CliRunner) -> None:
    """--katex and --kodlingvo katex are mutually exclusive."""
    result = runner.invoke(app, [
        "aldoni", "KtxSubj", "rdf:type", "--katex", "E=mc^2", "-L", "katex", "--jes",
    ])
    assert result.exit_code == 1
    assert "Ne eblas" in result.stdout or "Cannot use" in result.stdout


# ── File extension auto-detection ─────────────────────────────────────


def test_aldoni_str_dosiero_auto_detect_python(runner: CliRunner, tmp_path) -> None:
    """--str-dosiero foo.py without -L should auto-detect python."""
    runner.invoke(app, ["nodo", "aldoni", "PySubj", "-e", "eo::PySubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    py_file = tmp_path / "script.py"
    py_file.write_text("print('hello')\n")
    result = runner.invoke(app, [
        "aldoni", "PySubj", "rdf:type", "-D", str(py_file), "--jes",
    ])
    assert result.exit_code == 0, f"auto-detect .py failed: {result.stdout}"
    # Should show the MIME type in the success message
    assert "text/x-python" in result.stdout, f"Expected text/x-python in: {result.stdout}"


def test_aldoni_str_dosiero_auto_detect_javascript(runner: CliRunner, tmp_path) -> None:
    """--str-dosiero foo.js without -L should auto-detect javascript."""
    runner.invoke(app, ["nodo", "aldoni", "JsSubj", "-e", "eo::JsSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    js_file = tmp_path / "app.js"
    js_file.write_text("console.log(1);\n")
    result = runner.invoke(app, [
        "aldoni", "JsSubj", "rdf:type", "-D", str(js_file), "--jes",
    ])
    assert result.exit_code == 0, f"auto-detect .js failed: {result.stdout}"
    assert "text/javascript" in result.stdout


def test_aldoni_str_dosiero_auto_detect_html(runner: CliRunner, tmp_path) -> None:
    """--str-dosiero index.html without -L should auto-detect html."""
    runner.invoke(app, ["nodo", "aldoni", "HtmlSubj", "-e", "eo::HtmlSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    html_file = tmp_path / "index.html"
    html_file.write_text("<html></html>\n")
    result = runner.invoke(app, [
        "aldoni", "HtmlSubj", "rdf:type", "-D", str(html_file), "--jes",
    ])
    assert result.exit_code == 0, f"auto-detect .html failed: {result.stdout}"
    assert "text/html" in result.stdout


def test_aldoni_str_dosiero_unrecognised_extension_falls_to_plain(
    runner: CliRunner, tmp_path,
) -> None:
    """--str-dosiero foo.xyz without -L should fall back to text/plain."""
    runner.invoke(app, ["nodo", "aldoni", "XyzSubj", "-e", "eo::XyzSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    xyz_file = tmp_path / "data.xyz"
    xyz_file.write_text("some data\n")
    result = runner.invoke(app, [
        "aldoni", "XyzSubj", "rdf:type", "-D", str(xyz_file), "--jes",
    ])
    assert result.exit_code == 0, f"fallback .xyz failed: {result.stdout}"
    # Unrecognised extension → no MIME datatype;
    # the success message shows the plain literal directly.
    assert "kreita" in result.stdout.lower()


def test_aldoni_explicit_L_overrides_extension(runner: CliRunner, tmp_path) -> None:
    """Explicit -L should take precedence over file extension auto-detection."""
    runner.invoke(app, ["nodo", "aldoni", "OvrdSubj", "-e", "eo::OvrdSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    py_file = tmp_path / "script.py"
    py_file.write_text("print('overridden')\n")
    result = runner.invoke(app, [
        "aldoni", "OvrdSubj", "rdf:type", "-D", str(py_file), "--kodlingvo", "javascript", "--jes",
    ])
    assert result.exit_code == 0, f"explicit -L override failed: {result.stdout}"
    assert "text/javascript" in result.stdout


def test_aldoni_str_dosiero_auto_detect_tex(runner: CliRunner, tmp_path) -> None:
    """--str-dosiero formula.tex without -L should auto-detect latex."""
    runner.invoke(app, ["nodo", "aldoni", "TexSubj", "-e", "eo::TexSubj", "--jes"])
    runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

    tex_file = tmp_path / "formula.tex"
    tex_file.write_text("\\alpha + \\beta\n")
    result = runner.invoke(app, [
        "aldoni", "TexSubj", "rdf:type", "-D", str(tex_file), "--jes",
    ])
    assert result.exit_code == 0, f"auto-detect .tex failed: {result.stdout}"
    assert "text/x-tex" in result.stdout
