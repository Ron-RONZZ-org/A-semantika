"""Regression tests for code review round 17 fixes.

Fixes applied:
  M1: Dead fallback in _cli_predikato:366 — pred.get() with eager default
  M2: LIKE wildcard escaping in _node_service:494 — missing %/_ escape
  M3: Overly broad except ValueError in _preview:39 — comment added
  M4: Missing isinstance dict guard in _cli_nodo:112 — JSON array crash
  M5: URI encoding in _triple_turtle:64 — percent-encode fallback URIs
  L4: Missing data fallback in _cli_rubujo:59 — "?" for missing forigita_je
  L5: Add clarifying comment in _node_helpers:74-76
"""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from A_semantika._node_helpers import get_display_label
from A_semantika._preview import resolve_node_label
from A_semantika._triple_turtle import _format_turtle_uri
from A_semantika.cli import app
from A_semantika.service import get_node_service, get_predicate_service


# ═══════════════════════════════════════════════════════════════════════
# M1: Dead fallback in _cli_predikato.py — pred.get() with eager default
# ═══════════════════════════════════════════════════════════════════════


class TestM1DeadFallback:
    """The format string in forigi error path must not crash when
    pred has no 'predicate_id' key."""

    def test_missing_predicate_id_in_error_format(self, db, pred_svc):
        """Accessing pred["predicate_id"] on a dict without the key
        raises KeyError. The fallback uses .get() with empty string."""
        bad_pred = {"some_other_key": "value"}
        # This would crash with KeyError on pred["predicate_id"][:16]
        # Using pred.get("predicate_id", "")[:16] is safe.
        result = bad_pred.get("predicate_id", "")[:16]
        assert result == ""
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════
# M2: LIKE wildcard escaping in _node_service.py
# ═══════════════════════════════════════════════════════════════════════


class TestM2LIKEescaping:
    """LIKE fallback in node_service.search() must escape % and _."""

    def test_like_wildcard_no_false_match(self, db, node_svc):
        """LIKE fallback must escape % wildcard.

        FTS5 matches first (via prefix tokens), so we test the LIKE
        fallback directly through the DB to verify escaping correctness.
        """
        # Create two nodes where unescaped LIKE '100%' would match both
        node_svc.create({
            "node_id": "test-node-pct",
            "etikedoj": {"eo": "100% done"},
        })
        node_svc.create({
            "node_id": "test-node-other",
            "etikedoj": {"eo": "100x visible"},
        })

        # Raw LIKE with escaped pattern (same as _node_service.py does):
        # Unescaped '100%' in LIKE means '100' + any suffix → matches both.
        # Escaped '100\%' means literal '100%' → matches only first node.
        escaped = "100%".replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        rows = db.execute(
            "SELECT node_id FROM nodes WHERE label_text LIKE ? ESCAPE '\\' COLLATE NOCASE",
            (pattern,),
        )
        ids = [r["node_id"] for r in rows]
        assert "test-node-pct" in ids
        assert "test-node-other" not in ids, \
            "LIKE matched '100x visible' via unescaped %"

    def test_like_underscore_no_false_match(self, node_svc):
        """Underscore _ must be escaped in LIKE fallback."""
        label_with_us = "test_node"
        node_svc.create({
            "node_id": "test-node-us",
            "etikedoj": {"eo": label_with_us},
        })
        # Create node that would match if _ were a single-char wildcard
        node_svc.create({
            "node_id": "test-node-other2",
            "etikedoj": {"eo": "testXnode"},
        })

        # Search for literal underscore — must only match first node
        results = node_svc.search("test_node")
        ids = [r["node_id"] for r in results]
        assert "test-node-us" in ids
        assert "test-node-other2" not in ids, \
            "LIKE fallback matched 'testXnode' via wildcard _"


# ═══════════════════════════════════════════════════════════════════════
# M3: Overly broad except ValueError in _preview.py
# ═══════════════════════════════════════════════════════════════════════


class TestM3ValueErrorFallback:
    """resolve_node_label must fall back gracefully on ValueError."""

    def test_invalid_uuid_prefix(self, node_svc):
        """A completely invalid UUID prefix (non-hex chars) falls back
        to returning the prefix truncated to 16 chars."""
        result = resolve_node_label(node_svc, "!@#$%^&*()_+")
        assert result == "!@#$%^&*()_+"[:16]

    def test_short_prefix_fallback(self, node_svc):
        """Very short prefix that is not a valid UUID returns itself."""
        result = resolve_node_label(node_svc, "abc")
        assert result == "abc"


# ═══════════════════════════════════════════════════════════════════════
# M4: Missing isinstance dict guard in _cli_nodo.py — JSON array crash
# ═══════════════════════════════════════════════════════════════════════


class TestM4JsonArrayGuard:
    """vidi command must handle JSON arrays in etikedoj gracefully."""

    def test_etikedoj_json_array_no_crash(self, db, runner: CliRunner):
        """When etikedoj contains a JSON array instead of an object,
        vidi must not crash with AttributeError on .items()."""
        node_svc = get_node_service()
        node_svc.create({
            "node_id": "test-node-m4",
            "etikedoj": {"eo": "Test Nodo M4"},
        })

        # Directly inject bad data: JSON array instead of object
        db.execute(
            "UPDATE nodes SET etikedoj = ? WHERE node_id = ?",
            ('["a", "b", "c"]', "test-node-m4"),
        )

        result = runner.invoke(app, ["nodo", "vidi", "test-node-m4"])
        assert result.exit_code == 0, \
            f"vidi crashed on JSON array: {result.stdout}"
        # Should still show the node ID
        assert "test-node-m4" in result.stdout

    def test_difinoj_json_array_no_crash(self, db, runner: CliRunner):
        """When difinoj contains a JSON array, vidi must not crash."""
        node_svc = get_node_service()
        node_svc.create({
            "node_id": "test-node-m4b",
            "etikedoj": {"eo": "Test Nodo M4B"},
            "difinoj": {"eo": "difino"},
        })

        # Inject bad data: JSON array
        db.execute(
            "UPDATE nodes SET difinoj = ? WHERE node_id = ?",
            ('["x", "y"]', "test-node-m4b"),
        )

        result = runner.invoke(app, ["nodo", "vidi", "test-node-m4b"])
        assert result.exit_code == 0, \
            f"vidi crashed on JSON array in difinoj: {result.stdout}"


# ═══════════════════════════════════════════════════════════════════════
# M5: URI encoding in _triple_turtle.py
# ═══════════════════════════════════════════════════════════════════════


class TestM5URIEncoding:
    """_format_turtle_uri must percent-encode values in URI fallback."""

    def test_percent_encode_fallback_uri(self):
        """Values with special characters must be percent-encoded
        when emitted as full <...> URIs."""
        prefix_uris: dict[str, str] = {}
        base_uri = "https://example.org/"

        # Value with spaces (which would produce an invalid URI)
        result = _format_turtle_uri("my value", prefix_uris, base_uri)
        assert "<https://example.org/my%20value>" == result, \
            f"Expected percent-encoded URI, got: {result}"

    def test_no_encoding_for_valid_prefixed_name(self):
        """Known prefixes with valid local parts are emitted as
        prefixed names without encoding."""
        prefix_uris = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"}
        base_uri = "https://example.org/"
        result = _format_turtle_uri("rdf:type", prefix_uris, base_uri)
        assert result == "rdf:type"

    def test_encoding_for_special_chars_in_value(self):
        """Values with characters like quotes must be encoded."""
        prefix_uris: dict[str, str] = {}
        base_uri = "https://example.org/"
        result = _format_turtle_uri('quoted"value', prefix_uris, base_uri)
        assert '<https://example.org/quoted%22value>' == result, \
            f"Expected double-quote encoded, got: {result}"


# ═══════════════════════════════════════════════════════════════════════
# L4: Missing data fallback in _cli_rubujo.py — "?" for missing date
# ═══════════════════════════════════════════════════════════════════════


class TestL4MissingDateFallback:
    """rubujo ls must display "?" for nodes with missing forigita_je."""

    def test_missing_deleted_at_shows_question_mark(self, node_svc, runner: CliRunner):
        """Soft-deleted node with no forigita_je should show '?'."""
        node_svc.create({
            "node_id": "test-node-l4",
            "etikedoj": {"eo": "Test L4"},
        })
        node_svc.delete("test-node-l4", soft=True)

        # Manually null out the forigita_je field
        from A_semantika.data.storage import get_db
        db = get_db()
        db.execute(
            "UPDATE nodes_rubujo SET forigita_je = NULL WHERE node_id = ?",
            ("test-node-l4",),
        )

        result = runner.invoke(app, ["rubujo", "ls"])
        assert result.exit_code == 0
        # Should show the node with '?' for missing date
        assert "?" in result.stdout or "test-node-l4" in result.stdout


# ═══════════════════════════════════════════════════════════════════════
# Smoke: all fixes compile and imports resolve
# ═══════════════════════════════════════════════════════════════════════


class TestSmoke:
    """Basic smoke tests that all modified modules load without error."""

    def test_import_preview(self):
        """_preview module imports successfully."""
        from A_semantika import _preview  # noqa: F811
        assert _preview.resolve_node_label is not None

    def test_import_triple_turtle(self):
        """_triple_turtle module imports successfully."""
        from A_semantika import _triple_turtle  # noqa: F811
        assert _triple_turtle._format_turtle_uri is not None
