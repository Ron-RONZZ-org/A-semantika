"""Edge case and coverage gap tests for A-semantika.

Covers:
- FTS5 injection resistance (M1)
- UUID heuristic edge cases (M3)
- validate_type_flags() helper
- build_triple_preview_table() and confirm_node_with_arcs()
- Turtle export with custom datatypes
- Special chars in labels/literals
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from A_semantika.cli import app


# ── FTS5 Injection Resistance ─────────────────────────────────────────────────


class TestFTS5Sanitization:
    """FTS5 query sanitization should resist injection (M1)."""

    def test_search_with_special_chars(self, node_svc):
        """Special FTS5 chars should not crash search."""
        node_svc.create({"etikedoj": {"eo": "Testo-normala"}})

        # Various FTS5 special chars that previously could crash
        for query in [
            '" OR 1=1 --',
            '*',
            '^',
            '-',
            '+',
            '~',
            '(',
            ')',
            '{',
            '}',
            '[',
            ']',
            ':',
            '<',
            '>',
            '%',
            'a"b',
            'a*b',
            'a^b',
            'a-b',
            'a+b',
            'a~b',
        ]:
            # Should not raise fts5 syntax error
            results = node_svc.search(query)
            assert results is not None, f"Search with '{query}' returned None"

    def test_search_pure_special_chars(self, node_svc):
        """Pure special char queries should return all (sanitized to empty)."""
        node_svc.create({"etikedoj": {"eo": "Testo-123"}})
        # Query made entirely of special chars → sanitized to empty → list all
        results = node_svc.search("***^^^---")
        assert results is not None

    def test_search_mixed_special_and_normal(self, node_svc):
        """Normal text mixed with special chars should still match."""
        node_svc.create({"etikedoj": {"eo": "Esperanta Teksto"}})
        results = node_svc.search("Esperanta***^^^")
        assert len(results) >= 1


# ── UUID Heuristic Edge Cases ─────────────────────────────────────────────────


class TestUUIDHeuristic:
    """UUID heuristic should correctly classify inputs (M3)."""

    def test_short_labels_not_uuid(self):
        """Short labels like 'Hundo', 'tipo' should NOT look like UUIDs."""
        from A_semantika._triple_search import _looks_like_uuid_prefix

        short_labels = ["Hundo", "tipo", "kato", "birdo", "123", "abc", "a1"]
        for label in short_labels:
            assert not _looks_like_uuid_prefix(label), f"'{label}' should not look like UUID"

    def test_hex_uuid_prefixes_look_like_uuid(self):
        """Hex UUID prefixes (8+ chars) should look like UUIDs."""
        from A_semantika._triple_search import _looks_like_uuid_prefix

        valid_prefixes = [
            "a1b2c3d4",
            "12345678-",
            "abcdef01-",
            "deadbeef",
            "00000000-",
            "a1b2c3d4-",
            "a1b2c3d4-e5",
        ]
        for prefix in valid_prefixes:
            assert _looks_like_uuid_prefix(prefix), f"'{prefix}' should look like UUID"

    def test_non_hex_chars_not_uuid(self):
        """Text with non-hex characters should NOT look like UUID."""
        from A_semantika._triple_search import _looks_like_uuid_prefix

        non_uuid = [
            "HelloWorld",  # non-hex chars
            "zzzzzzzz",     # non-hex chars
            "test-1234",    # 't', 'e', 's' not hex
            "xxxxxxxx",     # non-hex
        ]
        for text in non_uuid:
            assert not _looks_like_uuid_prefix(text), f"'{text}' should not look like UUID"

    def test_uuid_prefix_too_short_not_uuid(self):
        """Very short hex strings (< 8 chars) should NOT look like UUID."""
        from A_semantika._triple_search import _looks_like_uuid_prefix

        short_hex = ["a1", "abc", "1234", "dead", "beef", "a1b2"]
        for text in short_hex:
            assert not _looks_like_uuid_prefix(text), f"'{text}' should not look like UUID"

    def test_uuid_prefix_too_long_not_uuid(self):
        """Strings > 12 chars should NOT look like UUID prefix."""
        from A_semantika._triple_search import _looks_like_uuid_prefix

        assert _looks_like_uuid_prefix("a1b2c3d4e5f6")  # 12 hex chars = OK (boundary)
        assert not _looks_like_uuid_prefix("a1b2c3d4e5f67")  # 13 hex chars = too long

    def test_resolve_uuid_prefix_with_hyphenated(self, node_svc):
        """UUID prefix with hyphens should resolve correctly."""
        uuid = "c0ffeec0-0000-0000-0000-000000000001"
        node_svc.create({"uuid": uuid, "etikedoj": {"eo": "Kafo"}})

        # Prefix without trailing hyphen
        from A_semantika._triple_search import resolve_subjects
        uuids = resolve_subjects(node_svc, uuid[:8])
        assert uuids == [uuid]


# ── validate_type_flags ───────────────────────────────────────────────────────


class TestValidateTypeFlags:
    """validate_type_flags() should validate combinations correctly."""

    def test_no_flags_returns_none(self):
        """No type flags should return None (URI reference)."""
        from A_semantika._cli_helpers import validate_type_flags

        result = validate_type_flags(False, False, False, False, None, None)
        assert result is None

    def test_str_flag(self):
        """--str should return None (string literal, no datatype)."""
        from A_semantika._cli_helpers import validate_type_flags

        result = validate_type_flags(True, False, False, False, None, None)
        assert result is None

    def test_int_flag(self):
        """--int should return xsd:integer."""
        from A_semantika._cli_helpers import validate_type_flags

        result = validate_type_flags(False, True, False, False, None, None)
        assert result == "xsd:integer"

    def test_float_flag(self):
        """--float should return xsd:decimal."""
        from A_semantika._cli_helpers import validate_type_flags

        result = validate_type_flags(False, False, True, False, None, None)
        assert result == "xsd:decimal"

    def test_bool_flag(self):
        """--bool should return xsd:boolean."""
        from A_semantika._cli_helpers import validate_type_flags

        result = validate_type_flags(False, False, False, True, None, None)
        assert result == "xsd:boolean"

    def test_multiple_flags_raises(self):
        """Combining multiple type flags should raise."""
        from A_semantika._cli_helpers import validate_type_flags

        with pytest.raises(Exception):
            validate_type_flags(True, True, False, False, None, None)

    def test_lingvo_without_str_warns(self):
        """--lingvo without --str should warn (returns URI)."""
        from A_semantika._cli_helpers import validate_type_flags

        # Should not raise, returns None (URI)
        result = validate_type_flags(False, False, False, False, "eo", None)
        assert result is None

    def test_unuo_without_numeric_warns(self):
        """--unuo without --int/--float should warn (returns URI)."""
        from A_semantika._cli_helpers import validate_type_flags

        result = validate_type_flags(False, False, False, False, None, "some-uuid")
        assert result is None


# ── Preview Table Tests ──────────────────────────────────────────────────────


class TestBuildTriplePreviewTable:
    """build_triple_preview_table() should produce correct tables."""

    def test_build_uri_preview(self, node_svc, pred_svc):
        """URI triple preview should show labels and raw IDs."""
        from A_semantika._preview import build_triple_preview_table

        subj = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        obj = node_svc.create({"etikedoj": {"eo": "Mamulo"}})
        pred = pred_svc.create({"predicate_id": "rdf:type", "etikedoj": {"eo": "tipo"}})

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["uuid"], "rdf:type", obj["uuid"],
            "uri",
        )
        assert table is not None
        assert "→ URI" in footnote

    def test_build_string_literal_preview(self, node_svc, pred_svc):
        """String literal preview should show quoted value."""
        from A_semantika._preview import build_triple_preview_table

        subj = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        pred = pred_svc.create({"predicate_id": "rdfs:label", "etikedoj": {"eo": "etikedo"}})

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["uuid"], "rdfs:label", "Hundo",
            "literal", object_lang="eo",
        )
        assert table is not None
        assert "→ literal" in footnote or "lang" in footnote

    def test_build_typed_literal_preview(self, node_svc, pred_svc):
        """Typed literal preview should show datatype."""
        subj = node_svc.create({"etikedoj": {"eo": "Urbo"}})
        unit = node_svc.create({"etikedoj": {"eo": "loĝantoj"}})
        pred = pred_svc.create({"predicate_id": "wdt:P1082", "etikedoj": {"eo": "loĝantaro"}})

        from A_semantika._preview import build_triple_preview_table

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["uuid"], "wdt:P1082", "1000000",
            "literal", object_datatype="xsd:integer", object_unit=unit["uuid"],
        )
        assert table is not None
        assert "integer" in footnote


class TestConfirmNodeWithArcs:
    """confirm_node_with_arcs() should handle arc previews."""

    def test_confirm_node_with_uri_arcs(self, node_svc, pred_svc):
        """Node with URI arcs should preview correctly."""
        from A_semantika._preview import confirm_node_with_arcs

        target = node_svc.create({"etikedoj": {"eo": "Mamulo"}})
        pred_svc.create({"predicate_id": "rdf:type", "etikedoj": {"eo": "tipo"}})

        node_uuid = "test-arc-node"
        node_svc.create({"uuid": node_uuid, "etikedoj": {"eo": "Hundo"}})

        arcs = [
            {
                "subject": node_uuid,
                "predicate": "rdf:type",
                "object": target["uuid"],
                "object_type": "uri",
            },
        ]
        # With yes=True, confirmation is skipped
        result = confirm_node_with_arcs(node_svc, pred_svc, "Hundo", node_uuid, arcs, yes=True)
        assert result is True


# ── CLI: Node with arc shortcuts ──────────────────────────────────────────────


class TestNodeAldoniWithArcs:
    """nodo aldoni with --tipo, --superklaso, --ne, --invers."""

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


# ── CLI: Triple modifi command ────────────────────────────────────────────────


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


# ── Turtle Export with Custom Datatypes ───────────────────────────────────────


class TestTurtleExportCustom:
    """Turtle export with custom datatypes (L4)."""

    def test_turtle_custom_datatype(self, node_svc, pred_svc, triple_svc):
        """Export with custom datatype should not use xsd: prefix."""
        subj = node_svc.create({"etikedoj": {"eo": "Testo"}})
        obj = node_svc.create({"etikedoj": {"eo": "TestObj"}})
        pred_svc.create({"predicate_id": "ex:customProp", "etikedoj": {"eo": "prop"}})

        triple_svc.add(
            subject_uuid=subj["uuid"],
            predicate_id="ex:customProp",
            object_value="42",
            object_type="literal",
            object_datatype="my:customType",
        )

        ttl = triple_svc.export_turtle()
        # Should use <my:customType> not xsd:customType
        assert "^^<my:customType>" in ttl or "my:customType" in ttl

    def test_turtle_xsd_datatype_unchanged(self, node_svc, pred_svc, triple_svc):
        """Export with xsd: datatype should still use xsd: prefix."""
        subj = node_svc.create({"etikedoj": {"eo": "Urbo"}})
        pred_svc.create({"predicate_id": "wdt:P1082", "etikedoj": {"eo": "loĝantaro"}})

        triple_svc.add(
            subject_uuid=subj["uuid"],
            predicate_id="wdt:P1082",
            object_value="1000000",
            object_type="literal",
            object_datatype="xsd:integer",
        )

        ttl = triple_svc.export_turtle()
        assert "^^xsd:integer" in ttl


# ── Edge Cases: Special chars in labels ──────────────────────────────────────


class TestSpecialCharsInData:
    """Edge cases with special characters."""

    def test_node_with_special_chars_label(self, runner: CliRunner):
        """Node with special chars in labels should work."""
        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", "eo::Testo kun ŝanĝoĵ!@#$%",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "kreita" in result.stdout or "Created" in result.stdout

    def test_triple_with_special_chars_literal(self, runner: CliRunner):
        """Triple with special chars in literal value should work."""
        subj_uuid = "f4000000-0000-0000-0000-000000000004"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::SpecSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:label", "-e", "eo::etikedo", "--jes"])

        result = runner.invoke(app, [
            "aldoni", subj_uuid[:8], "rdfs:label",
            'Testo with "quotes" & <html>',
            "--str", "--jes",
        ])
        assert result.exit_code == 0

    def test_long_label_value(self, runner: CliRunner):
        """Very long label values should not crash."""
        long_label = "A" * 500
        result = runner.invoke(app, [
            "nodo", "aldoni",
            "-e", f"eo::{long_label}",
            "--jes",
        ])
        assert result.exit_code == 0
        assert "kreita" in result.stdout or "Created" in result.stdout

    def test_very_long_literal(self, runner: CliRunner):
        """Very long literal values should not crash."""
        subj_uuid = "f5000000-0000-0000-0000-000000000005"
        runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::LongSubj", "--jes"])
        runner.invoke(app, ["predikato", "aldoni", "rdfs:comment", "-e", "eo::komento", "--jes"])

        long_value = "X" * 2000
        result = runner.invoke(app, [
            "aldoni", subj_uuid[:8], "rdfs:comment", long_value,
            "--str", "--jes",
        ])
        assert result.exit_code == 0


# ── Edge Cases: empty/trivial inputs ──────────────────────────────────────────


class TestEmptyInputs:
    """Empty or trivial inputs should not crash."""

    def test_nodo_serci_empty_string(self, runner: CliRunner):
        """Searching with empty string should not crash."""
        result = runner.invoke(app, ["nodo", "serci", ""])
        assert result.exit_code in (0, 2)

    def test_predikato_serci_empty(self, runner: CliRunner):
        """Predicate search with empty string should not crash."""
        result = runner.invoke(app, ["predikato", "serci", ""])
        assert result.exit_code in (0, 2)


# ── CLI: Triple modifi target selection ──────────────────────────────────────


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


# ── confirm_triple edge cases ─────────────────────────────────────────────────


class TestConfirmTriple:
    """confirm_triple() edge cases."""

    def test_confirm_triple_yes(self, node_svc, pred_svc):
        """confirm_triple with yes=True should skip confirmation."""
        from A_semantika._preview import confirm_triple

        subj = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        obj = node_svc.create({"etikedoj": {"eo": "Mamulo"}})
        pred_svc.create({"predicate_id": "rdf:type", "etikedoj": {"eo": "tipo"}})

        result = confirm_triple(
            node_svc, pred_svc,
            subj["uuid"], "rdf:type", obj["uuid"],
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
            subj["uuid"], "wdt:P1082", "1000000",
            "literal", object_datatype="xsd:integer",
            object_unit=unit["uuid"],
            yes=True,
        )
        assert result is True


# ── CLI: Validate predicate appears before confirmation (S2) ──────────────────


def test_predicate_validated_before_confirm(runner: CliRunner):
    """Predicate validation should happen BEFORE confirmation (S2)."""
    subj_uuid = "f7000000-0000-0000-0000-000000000007"
    obj_uuid = "f8000000-0000-0000-0000-000000000008"
    runner.invoke(app, ["nodo", "aldoni", subj_uuid, "-e", "eo::PreSubj", "--jes"])
    runner.invoke(app, ["nodo", "aldoni", obj_uuid, "-e", "eo::PreObj", "--jes"])

    # Using a nonexistent predicate should error before confirmation prompt
    # (no -y flag, but should error out before reaching confirm_action)
    result = runner.invoke(app, [
        "aldoni", subj_uuid[:8], "nonexistent:pred", obj_uuid[:8],
    ])
    assert result.exit_code == 1
    assert "ne trovita" in result.stdout or "not found" in result.stdout


# ── Multi-identifier forigi edge cases (Issue #13) ─────────────────────────────


class TestNodoForigiMulti:
    """Edge cases for multi-UUID nodo forigi."""

    def test_partial_failure_some_not_found(self, runner: CliRunner):
        """Some UUIDs not found should report errors but delete the rest."""
        runner.invoke(app, ["nodo", "aldoni", "a0000000-0000-0000-0000-000000000001", "-e", "eo::Exists1", "-y"])
        runner.invoke(app, ["nodo", "aldoni", "a0000000-0000-0000-0000-000000000002", "-e", "eo::Exists2", "-y"])
        result = runner.invoke(app, [
            "nodo", "forigi",
            "a0000000-0000-0000-0000-000000000001",
            "nonexistent-uuid",
            "a0000000-0000-0000-0000-000000000002",
            "-y",
        ])
        assert result.exit_code == 0
        assert "ne trovita" in result.stdout or "not found" in result.stdout
        assert "Forigis 2 el" in result.stdout or "Deleted 2 of" in result.stdout

    def test_all_not_found(self, runner: CliRunner):
        """All UUIDs not found should error."""
        result = runner.invoke(app, [
            "nodo", "forigi", "zzz-nonexistent-1", "zzz-nonexistent-2", "-y",
        ])
        assert result.exit_code == 1
        assert "Nenio forigebla" in result.stdout or "Nothing to delete" in result.stdout

    def test_no_args_shows_error(self, runner: CliRunner):
        """No args should show error about missing argument."""
        result = runner.invoke(app, ["nodo", "forigi"])
        assert result.exit_code in (1, 2)
        # Missing required argument should produce an error
        assert result.exit_code != 0


class TestPredikatoForigiMulti:
    """Edge cases for multi-predicate-id predikato forigi."""

    def test_partial_failure_some_not_found(self, runner: CliRunner):
        """Some predicate IDs not found should report errors but delete the rest."""
        runner.invoke(app, ["predikato", "aldoni", "wdt:P111", "-e", "eo::test111", "-y"])
        runner.invoke(app, ["predikato", "aldoni", "wdt:P112", "-e", "eo::test112", "-y"])
        result = runner.invoke(app, [
            "predikato", "forigi", "wdt:P111", "wdt:NOTEXIST", "wdt:P112", "-y",
        ])
        assert result.exit_code == 0
        assert "ne trovita" in result.stdout or "not found" in result.stdout
        assert "Forigis 2 el" in result.stdout or "Deleted 2 of" in result.stdout

    def test_all_not_found(self, runner: CliRunner):
        """All predicate IDs not found should error."""
        result = runner.invoke(app, [
            "predikato", "forigi", "wdt:NEVER1", "wdt:NEVER2", "-y",
        ])
        assert result.exit_code == 1
        assert "Nenio forigebla" in result.stdout or "Nothing to delete" in result.stdout


class TestPredikatGrupoForigiMulti:
    """Edge cases for multi-group-name predikat-grupo forigi."""

    def test_partial_failure_some_not_found(self, runner: CliRunner):
        """Some group names not found should report errors but delete the rest."""
        runner.invoke(app, ["predikat-grupo", "aldoni", "grp_exists", "-y"])
        result = runner.invoke(app, [
            "predikat-grupo", "forigi", "grp_exists", "grp_nonexistent", "-y",
        ])
        assert result.exit_code == 0
        assert "ne trovita" in result.stdout or "not found" in result.stdout
        assert "Forigis 1 el" in result.stdout or "Deleted 1 of" in result.stdout

    def test_all_not_found(self, runner: CliRunner):
        """All group names not found should error."""
        result = runner.invoke(app, [
            "predikat-grupo", "forigi", "no_such_group_1", "no_such_group_2", "-y",
        ])
        assert result.exit_code == 1
        assert "Nenio forigebla" in result.stdout or "Nothing to delete" in result.stdout


class TestNodoForigiAmbiguousUUID:
    """Ambiguous UUID prefix in multi-forigi should report per-item."""

    def test_ambiguous_prefix_reported(self, runner: CliRunner, node_svc):
        """Ambiguous prefix should report error and not block other deletions."""
        node_svc.create({"uuid": "bbbbbbbb-0000-0000-0000-000000000001", "etikedoj": {"eo": "AmbA"}})
        node_svc.create({"uuid": "bbbbbbba-0000-0000-0000-000000000001", "etikedoj": {"eo": "AmbB"}})
        node_svc.create({"uuid": "cccccccc-0000-0000-0000-000000000001", "etikedoj": {"eo": "Clear"}})

        # "bbbb" matches both AmbA and AmbB → ambiguous
        result = runner.invoke(app, [
            "nodo", "forigi", "bbbb", "cccccccc", "-y",
        ])
        assert result.exit_code == 0
        assert "ambigua" in result.stdout or "ambiguous" in result.stdout
        assert "Forigis 1 el" in result.stdout or "Deleted 1 of" in result.stdout
