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
        """String literal preview should show quoted value."""
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
