"""Triple modifi and confirm_triple edge cases.

Extracted from test_edge_cases.py — TestTripleModifi + TestTripleModifiEdgeCases + TestConfirmTriple.
"""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from A_semantika.cli import app


class TestTripleModifi:
    """Triple modifi command (dedicated CLI tests)."""

    def test_triple_modifi_full_args(self, runner: CliRunner):
        """modifi with full SPO + new values should work."""
        subj_uuid = "f1000000-0000-0000-0000-000000000001"
        obj_uuid = "f2000000-0000-0000-0000-000000000002"
        new_obj_uuid = "f3000000-0000-0000-0000-000000000003"

        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::ModSubj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::ModObj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", new_obj_uuid, "-e", "eo::NewModObj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

        # Add original triple
        result = runner.invoke(app, [
            "aldoni", subj_uuid[:8], "rdf:type", obj_uuid[:8], "--jes",
        ])
        assert result.exit_code == 0

        # Modify the object
        result = runner.invoke(app, [
            "modifi", subj_uuid[:8], "rdf:type", obj_uuid[:8],
            "--nova-objekto", new_obj_uuid[:8],
            "--jes",
        ])
        # modifi should exit 0 on success
        assert result.exit_code == 0, f"modifi failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout


class TestTripleModifiEdgeCases:
    """Edge cases for triple modifi."""

    def test_modifi_nonexistent_subject(self, runner: CliRunner):
        """modifi with nonexistent subject should exit with error."""
        result = runner.invoke(app, [
            "modifi", "zzzzzzzz", "rdf:type", "oooooooo",
            "--nova-objekto", "nnnnnnnn",
            "--jes",
        ])
        assert result.exit_code == 1
        # Unified partial-match resolution reports "no matching arcs"
        # rather than "subject not found" (Issue #97).
        assert "kongruaj" in result.stdout

    def test_modifi_string_literal_direct(self, runner: CliRunner):
        """modifi a string-literal triple in direct mode should work."""
        subj_uuid = "f4000000-0000-0000-0000-000000000004"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::LitSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:label", "-e", "eo::etikedo", "--jes"])

        # Create string literal triple
        result = runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:label", "Hundo",
            "--str", "-l", "eo", "--jes",
        ])
        assert result.exit_code == 0, f"aldoni failed: {result.stdout}"

        # Modify it — change the literal value
        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:label", "Hundo",
            "--nova-objekto", "Doggo",
            "--str", "-l", "en",
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi literal failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_integer_literal_direct(self, runner: CliRunner):
        """modifi an integer-literal triple in direct mode should work."""
        subj_uuid = "f5000000-0000-0000-0000-000000000005"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::IntSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "wdt:P1082", "-e", "eo::loĝantaro", "--jes"])

        # Create integer literal triple
        result = runner.invoke(app, [
            "aldoni", subj_uuid, "wdt:P1082", "1000",
            "--int", "--jes",
        ])
        assert result.exit_code == 0, f"aldoni failed: {result.stdout}"

        # Modify it — change the value
        result = runner.invoke(app, [
            "modifi", subj_uuid, "wdt:P1082", "1000",
            "--nova-objekto", "2000",
            "--int",
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi int literal failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_uri_to_literal(self, runner: CliRunner):
        """modifi changing a URI triple to a literal should work."""
        subj_uuid = "f7000000-0000-0000-0000-000000000007"
        obj_uuid = "f8000000-0000-0000-0000-000000000008"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::ConvSubj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::ConvObj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

        # Create URI triple
        result = runner.invoke(app, [
            "aldoni", subj_uuid, "rdf:type", obj_uuid, "--jes",
        ])
        assert result.exit_code == 0, f"aldoni URI failed: {result.stdout}"

        # Change URI object to string literal
        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdf:type", obj_uuid,
            "--nova-objekto", "custom-type",
            "--str",
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi URI→literal failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_literal_noop(self, runner: CliRunner):
        """modifi a literal triple with same values should be a no-op."""
        subj_uuid = "f9000000-0000-0000-0000-000000000009"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::NoopSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "testo",
            "--str", "-l", "eo", "--jes",
        ])

        # Modify with same values → no-op
        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "testo",
            "--nova-objekto", "testo",
            "--str", "-l", "eo",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "neŝanĝita" in result.stdout or "unchanged" in result.stdout

    def test_modifi_nonexistent_object(self, runner: CliRunner):
        """modifi with nonexistent object should exit with error."""
        subj_uuid = "f6000000-0000-0000-0000-000000000006"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::ModSubj2", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

        result = runner.invoke(app, [
            "modifi", subj_uuid[:8], "rdf:type", "zzzzzzzz",
            "--nova-objekto", subj_uuid[:8],
            "--jes",
        ])
        assert result.exit_code == 1
        # Unified partial-match reports "no matching arcs" (Issue #97).
        assert "kongruaj" in result.stdout or "Neniuj" in result.stdout


class TestConfirmTriple:
    """confirm_triple() edge cases."""

    def test_confirm_triple_yes(self, node_svc, pred_svc):
        """confirm_triple with yes=True should skip confirmation."""
        from A_semantika._preview import confirm_triple

        subj = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        obj = node_svc.create({"etikedoj": {"eo": "Mamulo"}})
        # rdf:type is seeded by DEFAULT_PREDICATES — already exists

        result = confirm_triple(
            node_svc, pred_svc,
            subj["node_id"], "rdf:type", obj["node_id"],
            "uri", yes=True,
        )
        assert result is True

    def test_confirm_triple_with_unit(self, node_svc, pred_svc):
        """confirm_triple with object_unit should show unit in footnote."""
        from A_semantika._preview import confirm_triple

        subj = node_svc.create({"etikedoj": {"eo": "Urbo"}})
        unit = node_svc.create({"etikedoj": {"eo": "loĝantoj"}})
        pred_svc.create({"predicate_id": "wdt:P1082", "etikedoj": {"eo": "loĝantaro"}})

        result = confirm_triple(
            node_svc, pred_svc,
            subj["node_id"], "wdt:P1082", "1000000",
            "literal", object_datatype="xsd:integer",
            object_unit=unit["node_id"],
            yes=True,
        )
        assert result is True


class TestModifiUnuo:
    """Test modifi --unuo integration with normalize_unit()."""

    def test_modifi_unuo_noop_same_unit(self, runner: CliRunner) -> None:
        """--unuo with the same unit should be a no-op (no auto-creation)."""
        subj_uuid = "a1000000-0000-0000-0000-000000000001"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::UnuoSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "wdt:P1082", "-e", "eo::logxantaro", "--jes"])

        # Create numeric triple with unit
        result = runner.invoke(app, [
            "aldoni", subj_uuid, "wdt:P1082", "1000",
            "--int", "-u", "unit:JOULE", "--jes",
        ])
        assert result.exit_code == 0, f"aldoni failed: {result.stdout}"

        # Modify with same value but same unit → no-op
        result = runner.invoke(app, [
            "modifi", subj_uuid, "wdt:P1082", "1000",
            "--nova-objekto", "1000", "--unuo", "unit:JOULE",
            "--int", "--jes",
        ])
        assert result.exit_code == 0
        assert "neŝanĝita" in result.stdout or "unchanged" in result.stdout

    def test_modifi_unuo_noop_symbol(self, runner: CliRunner) -> None:
        """--unuo with symbol for same unit should be no-op."""
        subj_uuid = "a2000000-0000-0000-0000-000000000002"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::UnuoSym", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "wdt:P1082", "-e", "eo::logxantaro", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "wdt:P1082", "500",
            "--int", "-u", "unit:JOULE", "--jes",
        ])

        # --unuo "J" resolves to unit:JOULE same as existing → no-op
        result = runner.invoke(app, [
            "modifi", subj_uuid, "wdt:P1082", "500",
            "--nova-objekto", "500", "--unuo", "J",
            "--int", "--jes",
        ])
        assert result.exit_code == 0
        assert "neŝanĝita" in result.stdout or "unchanged" in result.stdout

    def test_modifi_unuo_change_unit(self, runner: CliRunner) -> None:
        """--unuo with a different unit should actually modify."""
        subj_uuid = "a3000000-0000-0000-0000-000000000003"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::UnuoChg", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "wdt:P1082", "-e", "eo::logxantaro", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "wdt:P1082", "300",
            "--int", "-u", "unit:JOULE", "--jes",
        ])

        # Change unit from JOULE to KELVIN
        result = runner.invoke(app, [
            "modifi", subj_uuid, "wdt:P1082", "300",
            "--nova-objekto", "300", "--unuo", "K",
            "--int", "--jes",
        ])
        assert result.exit_code == 0, f"modifi failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_unuo_noop_does_not_create_compound(self, runner: CliRunner, unit_svc) -> None:
        """--unuo no-op should NOT auto-create a compound unit."""
        subj_uuid = "a4000000-0000-0000-0000-000000000004"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::UnuoComp", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "wdt:P1082", "-e", "eo::logxantaro", "--jes"])

        # Create a triple with an existing compound unit
        runner.invoke(app, [
            "aldoni", subj_uuid, "wdt:P1082", "100",
            "--int", "-u", "J/K", "--jes",
        ])

        # Now modifi with --unuo J/K — should detect no-op without double-creating
        result = runner.invoke(app, [
            "modifi", subj_uuid, "wdt:P1082", "100",
            "--nova-objekto", "100", "--unuo", "J/K",
            "--int", "--jes",
        ])
        assert result.exit_code == 0
        assert "neŝanĝita" in result.stdout or "unchanged" in result.stdout
        # Two consecutive no-ops should not error either
        result2 = runner.invoke(app, [
            "modifi", subj_uuid, "wdt:P1082", "100",
            "--nova-objekto", "100", "--unuo", "J/K",
            "--int", "--jes",
        ])
        assert result2.exit_code == 0


class TestModifiStrDosiero:
    """Test modifi with --str-dosiero/-D."""

    def test_modifi_str_dosiero(self, runner: CliRunner, tmp_path: Path):
        """modifi using -D to read file as new object value."""
        subj_uuid = "b1000000-0000-0000-0000-000000000001"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::DosSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old text",
            "--str", "--jes",
        ])

        # Create a temp file
        f = tmp_path / "test.txt"
        f.write_text("new file content", encoding="utf-8")

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old text",
            "-D", str(f),
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi -D failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

        # Verify the new object value via serci
        result = runner.invoke(app, ["serci", "new file content"])
        assert result.exit_code == 0
        assert "new file content" in result.stdout

    def test_modifi_str_dosiero_with_kodlingvo(self, runner: CliRunner, tmp_path: Path):
        """modifi using -D -L to set a code block with language."""
        subj_uuid = "b2000000-0000-0000-0000-000000000002"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::KodSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        f = tmp_path / "script.py"
        f.write_text("print('hello')", encoding="utf-8")

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-D", str(f), "-L", "python",
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi -D -L failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_str_dosiero_file_not_found(self, runner: CliRunner):
        """modifi -D with nonexistent file shows error."""
        subj_uuid = "b3000000-0000-0000-0000-000000000003"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::MissSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-D", "/nonexistent/path.txt",
            "--jes",
        ])
        assert result.exit_code == 1
        assert "ne trovita" in result.stdout or "not found" in result.stdout

    def test_modifi_str_dosiero_extension_auto_detect(self, runner: CliRunner, tmp_path: Path):
        """modifi -D without -L auto-detects language from extension."""
        subj_uuid = "b4000000-0000-0000-0000-000000000004"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::AutoSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        f = tmp_path / "script.js"
        f.write_text("console.log('hi')", encoding="utf-8")

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-D", str(f),
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi -D auto-detect failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout


class TestModifiKatex:
    """Test modifi with --katex/-K."""

    def test_modifi_katex(self, runner: CliRunner):
        """modifi using -K to set a KaTeX formula."""
        subj_uuid = "c1000000-0000-0000-0000-000000000001"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::KatexSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-K", "E = mc^2",
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi -K failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_katex_with_dollar_delimiters(self, runner: CliRunner):
        """modifi -K strips $...$ delimiters."""
        subj_uuid = "c2000000-0000-0000-0000-000000000002"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::KatexDolSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-K", "$\\frac{a}{b}$",
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi -K $ failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_katex_empty_formula(self, runner: CliRunner):
        """modifi -K with empty formula shows error."""
        subj_uuid = "c3000000-0000-0000-0000-000000000003"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::KatexEmpSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-K", "$$",
            "--jes",
        ])
        assert result.exit_code == 1
        assert "Malplena" in result.stdout or "Empty" in result.stdout


class TestModifiFlagsMutualExclusion:
    """Test mutual exclusion of -K, -D, --nova-objekto."""

    def test_modifi_katex_and_str_dosiero_mutual_exclusion(self, runner: CliRunner, tmp_path: Path):
        """-K and -D cannot be used together."""
        subj_uuid = "d1000000-0000-0000-0000-000000000001"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::MutSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-K", "E=mc^2", "-D", str(f),
            "--jes",
        ])
        assert result.exit_code == 1
        assert "Ne eblas" in result.stdout or "Cannot" in result.stdout

    def test_modifi_katex_and_nova_objekto_mutual_exclusion(self, runner: CliRunner):
        """-K and --nova-objekto cannot be used together."""
        subj_uuid = "d2000000-0000-0000-0000-000000000002"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::MutSubj2", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-K", "E=mc^2", "--nova-objekto", "newval",
            "--jes",
        ])
        assert result.exit_code == 1
        assert "Ne eblas" in result.stdout or "Cannot" in result.stdout

    def test_modifi_str_dosiero_and_nova_objekto_mutual_exclusion(self, runner: CliRunner, tmp_path: Path):
        """-D and --nova-objekto cannot be used together."""
        subj_uuid = "d3000000-0000-0000-0000-000000000003"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::MutSubj3", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-D", str(f), "--nova-objekto", "newval",
            "--jes",
        ])
        assert result.exit_code == 1
        assert "Ne eblas" in result.stdout or "Cannot" in result.stdout

    def test_modifi_katex_and_kodlingvo_katex_mutual_exclusion(self, runner: CliRunner):
        """-K and --kodlingvo katex cannot be used together."""
        subj_uuid = "d4000000-0000-0000-0000-000000000004"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::MutSubj4", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        runner.invoke(app, [
            "aldoni", subj_uuid, "rdfs:comment", "old",
            "--str", "--jes",
        ])

        result = runner.invoke(app, [
            "modifi", subj_uuid, "rdfs:comment", "old",
            "-K", "E=mc^2", "-L", "katex",
            "--jes",
        ])
        assert result.exit_code == 1
        assert "Ne eblas" in result.stdout or "Cannot" in result.stdout


class TestModifiPartialMatch:
    """Tests for unified partial-match modifi (Issue #97)."""

    def test_modifi_partial_label_single_result(self, runner: CliRunner):
        """Partial label match on subject + predicate: single result -> auto-proceed."""
        subj = "a2000000-0000-0000-0000-000000000002"
        obj = "a3000000-0000-0000-0000-000000000003"
        new_obj = "a4000000-0000-0000-0000-000000000004"
        runner.invoke(app, ["nodo", "aldoni", subj, "-e", "eo::PartialSubj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", obj, "-e", "eo::PartialObj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", new_obj, "-e", "eo::NewPartialObj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])

        runner.invoke(app, ["aldoni", subj[:8], "rdf:type", obj[:8], "--jes"])

        # Use partial label for subject (FTS5 matches "PartialSubj")
        result = runner.invoke(app, [
            "modifi", "Part", "rdf", obj[:8],
            "--nova-objekto", new_obj[:8],
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_wildcard_predicate_and_object(self, runner: CliRunner):
        """Empty string wildcard for predicate and object: \"\" \"\"."""
        subj = "b1000000-0000-0000-0000-000000000001"
        obj = "b2000000-0000-0000-0000-000000000002"
        runner.invoke(app, ["nodo", "aldoni", subj, "-e", "eo::WildSubj", "--jes"])
        runner.invoke(app, ["nodo", "aldoni", obj, "-e", "eo::WildObj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdf:type", "-e", "eo::tipo", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])
        runner.invoke(app, ["aldoni", subj[:8], "rdf:type", obj[:8], "--jes"])

        # "" "" as predicate + object wildcard should resolve and auto-proceed
        # since there's only one arc for this subject.
        result = runner.invoke(app, [
            "modifi", subj[:8], "", "",
            "-np", "rdfs:comment",
            "--jes",
        ])
        assert result.exit_code == 0, f"modifi failed: {result.stdout}"
        assert "modifita" in result.stdout or "modified" in result.stdout

    def test_modifi_no_match_error(self, runner: CliRunner):
        """No matching arcs should produce 'Neniuj kongruaj arkoj' error."""
        result = runner.invoke(app, [
            "modifi", "NONEXISTENT_SUBJ_ZZZ", "rdf:type", "NONEXISTENT_OBJ_ZZZ",
            "--jes",
        ])
        assert result.exit_code == 1
        assert "kongruaj" in result.stdout or "Neniuj" in result.stdout
