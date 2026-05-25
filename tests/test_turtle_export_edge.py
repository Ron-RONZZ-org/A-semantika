"""Turtle export with custom datatypes and predicate validation edge cases.

Extracted from test_edge_cases.py — TestTurtleExportCustom + test_predicate_validated_before_confirm.
"""
from __future__ import annotations

from typer.testing import CliRunner

from A_semantika.cli import app


class TestTurtleExportCustom:
    """Turtle export with custom datatypes (L4)."""

    def test_turtle_custom_datatype(self, node_svc, pred_svc, triple_svc):
        """Export with custom datatype should not use xsd: prefix."""
        subj = node_svc.create({"etikedoj": {"eo": "Testo"}})
        obj = node_svc.create({"etikedoj": {"eo": "TestObj"}})
        pred_svc.create({"predicate_id": "ex:customProp", "etikedoj": {"eo": "prop"}})

        triple_svc.add(
            subject_uuid=subj["node_id"],
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
            subject_uuid=subj["node_id"],
            predicate_id="wdt:P1082",
            object_value="1000000",
            object_type="literal",
            object_datatype="xsd:integer",
        )

        ttl = triple_svc.export_turtle()
        assert "^^xsd:integer" in ttl


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
