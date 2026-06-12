"""UUID heuristic and validate_type_flags edge cases.

Extracted from test_edge_cases.py — TestUUIDHeuristic + TestValidateTypeFlags.
"""
from __future__ import annotations

import pytest
import typer


class TestUUIDHeuristic:
    """UUID heuristic should correctly classify inputs (M3)."""

    def test_short_labels_not_uuid(self):
        """Short labels like 'Hundo', 'tipo' should NOT look like UUIDs."""
        from A_semantika._constants import looks_like_uuid_prefix

        short_labels = ["Hundo", "tipo", "kato", "birdo", "123", "abc", "a1"]
        for label in short_labels:
            assert not looks_like_uuid_prefix(label), f"'{label}' should not look like UUID"

    def test_hex_uuid_prefixes_look_like_uuid(self):
        """Hex UUID prefixes (8+ chars) should look like UUIDs."""
        from A_semantika._constants import looks_like_uuid_prefix

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
            assert looks_like_uuid_prefix(prefix), f"'{prefix}' should look like UUID"

    def test_non_hex_chars_not_uuid(self):
        """Text with non-hex characters should NOT look like UUID."""
        from A_semantika._constants import looks_like_uuid_prefix

        non_uuid = [
            "HelloWorld",  # non-hex chars
            "zzzzzzzz",     # non-hex chars
            "test-1234",    # 't', 'e', 's' not hex
            "xxxxxxxx",     # non-hex
        ]
        for text in non_uuid:
            assert not looks_like_uuid_prefix(text), f"'{text}' should not look like UUID"

    def test_uuid_prefix_too_short_not_uuid(self):
        """Very short hex strings (< 8 chars) should NOT look like UUID."""
        from A_semantika._constants import looks_like_uuid_prefix

        short_hex = ["a1", "abc", "1234", "dead", "beef", "a1b2"]
        for text in short_hex:
            assert not looks_like_uuid_prefix(text), f"'{text}' should not look like UUID"

    def test_uuid_prefix_too_long_not_uuid(self):
        """Strings > 16 chars should NOT look like UUID prefix."""
        from A_semantika._constants import looks_like_uuid_prefix

        assert looks_like_uuid_prefix("a1b2c3d4e5f6789a")  # 16 hex chars = OK (boundary)
        assert not looks_like_uuid_prefix("a1b2c3d4e5f6789ab")  # 17 hex chars = too long

    def test_resolve_node_id_prefix_with_hyphenated(self, node_svc):
        """UUID prefix with hyphens should resolve correctly."""
        uuid = "c0ffeec0-0000-0000-0000-000000000001"
        node_svc.create({"node_id": uuid, "etikedoj": {"eo": "Kafo"}})

        # Prefix without trailing hyphen
        from A_semantika._triple_search import resolve_subjects
        uuids = resolve_subjects(node_svc, uuid[:16])
        assert uuids == [uuid]


class TestValidateTypeFlags:
    """validate_type_flags() should validate combinations correctly."""

    def test_no_flags_returns_uri(self):
        """No type flags should return (None, 'uri') (URI reference)."""
        from A_semantika._cli_helpers import validate_type_flags

        datatype, obj_type = validate_type_flags(False, False, False, False, None, None)
        assert datatype is None
        assert obj_type == "uri"

    def test_str_flag(self):
        """--str should return (None, 'literal') (string literal, no datatype)."""
        from A_semantika._cli_helpers import validate_type_flags

        datatype, obj_type = validate_type_flags(True, False, False, False, None, None)
        assert datatype is None
        assert obj_type == "literal"

    def test_int_flag(self):
        """--int should return ('xsd:integer', 'literal')."""
        from A_semantika._cli_helpers import validate_type_flags

        datatype, obj_type = validate_type_flags(False, True, False, False, None, None)
        assert datatype == "xsd:integer"
        assert obj_type == "literal"

    def test_float_flag(self):
        """--float should return ('xsd:decimal', 'literal')."""
        from A_semantika._cli_helpers import validate_type_flags

        datatype, obj_type = validate_type_flags(False, False, True, False, None, None)
        assert datatype == "xsd:decimal"
        assert obj_type == "literal"

    def test_bool_flag(self):
        """--bool should return ('xsd:boolean', 'literal')."""
        from A_semantika._cli_helpers import validate_type_flags

        datatype, obj_type = validate_type_flags(False, False, False, True, None, None)
        assert datatype == "xsd:boolean"
        assert obj_type == "literal"

    def test_multiple_flags_raises(self):
        """Combining multiple type flags should raise typer.Exit."""
        from A_semantika._cli_helpers import validate_type_flags

        with pytest.raises((typer.Exit, SystemExit)):
            validate_type_flags(True, True, False, False, None, None)

    def test_lingvo_without_str_raises(self):
        """--lingvo without --str should raise Exit (B3)."""
        from A_semantika._cli_helpers import validate_type_flags

        with pytest.raises((typer.Exit, SystemExit)):
            validate_type_flags(False, False, False, False, "eo", None)

    def test_unuo_without_numeric_raises(self):
        """--unuo without --int/--float should raise Exit (B3)."""
        from A_semantika._cli_helpers import validate_type_flags

        with pytest.raises((typer.Exit, SystemExit)):
            validate_type_flags(False, False, False, False, None, "some-uuid")
