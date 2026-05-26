"""Preview table and confirm_node_with_arcs edge cases.

Extracted from test_edge_cases.py — TestBuildTriplePreviewTable + TestConfirmNodeWithArcs.
"""
from __future__ import annotations


class TestBuildTriplePreviewTable:
    """build_triple_preview_table() should produce correct tables."""

    def test_build_uri_preview(self, node_svc, pred_svc):
        """URI triple preview should show labels and raw IDs."""
        from A_semantika._preview import build_triple_preview_table

        subj = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        obj = node_svc.create({"etikedoj": {"eo": "Mamulo"}})
        # rdf:type is seeded by DEFAULT_PREDICATES — already exists

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["node_id"], "rdf:type", obj["node_id"],
            "uri",
        )
        assert table is not None
        assert "→ URI" in footnote

    def test_build_string_literal_preview(self, node_svc, pred_svc):
        """String literal preview must show value on Row 1, not Row 2."""
        from io import StringIO

        from rich.console import Console

        from A_semantika._preview import build_triple_preview_table

        subj = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        pred = pred_svc.create({"predicate_id": "rdfs:label", "etikedoj": {"eo": "etikedo"}})

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["node_id"], "rdfs:label", "Hundo",
            "literal", object_lang="eo",
        )
        assert table is not None
        assert "→ literal" in footnote or "lang" in footnote

        # Verify row order: quoted value must appear before raw subject ID
        buf = StringIO()
        console = Console(file=buf, width=120)
        console.print(table)
        output = buf.getvalue()

        value_pos = output.index('"Hundo"')
        raw_id_pos = output.index(subj["node_id"][:16])
        assert value_pos < raw_id_pos, (
            "String literal value must appear on Row 1 (before raw subject ID), "
            f"but value at {value_pos} comes after raw ID at {raw_id_pos}"
        )

    def test_build_typed_literal_preview(self, node_svc, pred_svc):
        """Typed literal preview should show datatype."""
        subj = node_svc.create({"etikedoj": {"eo": "Urbo"}})
        unit = node_svc.create({"etikedoj": {"eo": "loĝantoj"}})
        pred = pred_svc.create({"predicate_id": "wdt:P1082", "etikedoj": {"eo": "loĝantaro"}})

        from A_semantika._preview import build_triple_preview_table

        table, footnote = build_triple_preview_table(
            node_svc, pred_svc,
            subj["node_id"], "wdt:P1082", "1000000",
            "literal", object_datatype="xsd:integer", object_unit=unit["node_id"],
        )
        assert table is not None
        assert "integer" in footnote


class TestConfirmNodeWithArcs:
    """confirm_node_with_arcs() should handle arc previews."""

    def test_confirm_node_with_uri_arcs(self, node_svc, pred_svc) -> None:
        """Node with URI arcs should preview correctly."""
        from A_semantika._preview import confirm_node_with_arcs

        target = node_svc.create({"etikedoj": {"eo": "Mamulo"}})
        # rdf:type is seeded by DEFAULT_PREDICATES — already exists

        node_uuid = "test-arc-node"
        node_svc.create({"node_id": node_uuid, "etikedoj": {"eo": "Hundo"}})

        arcs = [
            {
                "subject": node_uuid,
                "predicate": "rdf:type",
                "object": target["node_id"],
                "object_type": "uri",
            },
        ]
        # With yes=True, confirmation is skipped
        result = confirm_node_with_arcs(node_svc, pred_svc, "Hundo", node_uuid, arcs, yes=True)
        assert result is True


# ── Q1: resolve_predicate_label refactored ―――――――――――――――――――――――――


class TestResolvePredicateLabel:
    """resolve_predicate_label() now delegates to storage.label_from_json()."""

    def test_returns_eo_label(self, pred_svc):
        """Should return the eo label from etikedoj JSON."""
        from A_semantika._preview import resolve_predicate_label

        label = resolve_predicate_label(pred_svc, "rdf:type")
        assert label == "tipo"

    def test_returns_predicate_id_when_no_label(self, pred_svc):
        """Should return predicate_id if etikedoj has no usable label."""
        from A_semantika._preview import resolve_predicate_label

        pred_svc.create({"predicate_id": "ex:custom", "etikedoj": {}})
        label = resolve_predicate_label(pred_svc, "ex:custom")
        assert label == "ex:custom"

    def test_returns_predicate_id_when_not_found(self, pred_svc):
        """Should return predicate_id if predicate doesn't exist."""
        from A_semantika._preview import resolve_predicate_label

        label = resolve_predicate_label(pred_svc, "wdt:NOTEXIST")
        assert label == "wdt:NOTEXIST"

    def test_falls_back_to_en_when_no_eo(self, pred_svc):
        """Should fall back to en when eo label is missing."""
        from A_semantika._preview import resolve_predicate_label

        pred_svc.create({"predicate_id": "ex:enonly", "etikedoj": {"en": "English Only"}})
        label = resolve_predicate_label(pred_svc, "ex:enonly")
        assert label == "English Only"


# ── Q4: resolve_node_label_from_node cached helper ───────────────────────


class TestResolveNodeLabelFromNode:
    """resolve_node_label_from_node() should extract labels from pre-resolved nodes."""

    def test_returns_eo_label(self):
        """Should return eo label from node dict."""
        from A_semantika._preview import resolve_node_label_from_node

        node = {"node_id": "abc123", "etikedoj": '{"eo": "Hundo", "en": "Dog"}'}
        label = resolve_node_label_from_node(node)
        assert label == "Hundo"

    def test_falls_back_to_en_when_no_eo(self):
        """Should fall back to en when eo is missing."""
        from A_semantika._preview import resolve_node_label_from_node

        node = {"node_id": "abc123", "etikedoj": '{"en": "Dog"}'}
        label = resolve_node_label_from_node(node)
        assert label == "Dog"

    def test_falls_back_to_id_when_no_labels(self):
        """Should fall back to node_id prefix when no labels."""
        from A_semantika._preview import resolve_node_label_from_node

        node = {"node_id": "abc123-def-456", "etikedoj": "{}"}
        label = resolve_node_label_from_node(node)
        assert label == "abc123-def-456"[:16]

    def test_falls_back_to_id_when_etikedoj_invalid(self):
        """Should fall back to node_id when etikedoj is invalid JSON."""
        from A_semantika._preview import resolve_node_label_from_node

        node = {"node_id": "abc123", "etikedoj": "not-json"}
        label = resolve_node_label_from_node(node)
        assert label == "abc123"

    def test_works_with_already_parsed_labels(self):
        """Should handle already-parsed dict as etikedoj."""
        from A_semantika._preview import resolve_node_label_from_node

        node = {"node_id": "abc123", "etikedoj": {"eo": "Hundo"}}
        label = resolve_node_label_from_node(node)
        assert label == "Hundo"


# ── build_modify_preview coverage ─────────────────────────────────────


class TestBuildModifyPreview:
    """build_modify_preview() should produce correct old→new tables."""

    def test_build_uri_preview(self, node_svc, pred_svc):
        """URI triple modifi preview should show labels and raw IDs."""
        from io import StringIO

        from rich.console import Console

        from A_semantika._cli_helpers import build_modify_preview

        subj = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        obj = node_svc.create({"etikedoj": {"eo": "Mamulo"}})
        new_subj = node_svc.create({"etikedoj": {"eo": "Lupo"}})

        table = build_modify_preview(
            node_svc, pred_svc,
            subj["node_id"], "rdf:type", obj["node_id"],
            "uri", None,
            new_subj["node_id"], "rdfs:label", obj["node_id"],
            "uri", None,
        )
        assert table is not None
        buf = StringIO()
        console = Console(file=buf, width=120)
        console.print(table)
        output = buf.getvalue()
        assert "Malnova" in output or "Old" in output
        assert "Nova" in output or "New" in output

    def test_build_literal_preview(self, node_svc, pred_svc):
        """Literal triple modifi preview should show quoted value."""
        from io import StringIO

        from rich.console import Console

        from A_semantika._cli_helpers import build_modify_preview

        subj = node_svc.create({"etikedoj": {"eo": "Hundo"}})
        new_subj = node_svc.create({"etikedoj": {"eo": "Lupo"}})

        table = build_modify_preview(
            node_svc, pred_svc,
            subj["node_id"], "rdfs:label", "Malnova Etikedo",
            "literal", "eo",
            new_subj["node_id"], "rdfs:label", "Nova Etikedo",
            "literal", "eo",
        )
        assert table is not None
        buf = StringIO()
        console = Console(file=buf, width=120)
        console.print(table)
        output = buf.getvalue()
        assert "Malnova Etikedo" in output or "Nova Etikedo" in output
