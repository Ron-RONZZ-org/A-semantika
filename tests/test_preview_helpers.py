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

    def test_confirm_node_with_uri_arcs(self, node_svc, pred_svc):
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
