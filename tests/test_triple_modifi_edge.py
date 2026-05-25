"""Triple modifi and confirm_triple edge cases.

Extracted from test_edge_cases.py — TestTripleModifi + TestTripleModifiEdgeCases + TestConfirmTriple.
"""
from __future__ import annotations

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
        assert "ne trovita" in result.stdout or "not found" in result.stdout

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
        assert "ne trovita" in result.stdout or "not found" in result.stdout


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
