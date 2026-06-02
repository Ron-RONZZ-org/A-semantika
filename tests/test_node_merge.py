"""Tests for NodeService.merge_nodes() — node merge functionality."""
from __future__ import annotations

import json


class TestNodeMerge:
    """NodeService.merge_nodes() tests."""

    def test_merge_basic(self, node_svc) -> None:
        """Merging source into target should reassign triples and delete source."""
        src = node_svc.create({"node_id": "SRC", "etikedoj": {"eo": "Fonto"}})
        tgt = node_svc.create({"node_id": "TGT", "etikedoj": {"eo": "Celo"}})

        from A_semantika.service import get_triple_service

        triple_svc = get_triple_service()
        triple_svc.add(src["node_id"], "rdf:type", tgt["node_id"], "uri")

        assert triple_svc.count_by_subject_or_object(src["node_id"]) == 1

        merged = node_svc.merge_nodes(src["node_id"], tgt["node_id"])

        assert node_svc.get(src["node_id"]) is None
        assert merged["node_id"] == tgt["node_id"]
        assert triple_svc.count_by_subject_or_object(tgt["node_id"]) == 1
        triples = triple_svc.get_by_subject(tgt["node_id"])
        assert len(triples) == 1
        assert triples[0]["subject_uuid"] == tgt["node_id"]

    def test_merge_labels_target_first(self, node_svc) -> None:
        """Label merge should keep target values on conflict (target-first)."""
        src = node_svc.create({
            "node_id": "SRC_LBL",
            "etikedoj": {"eo": "Homo", "en": "Human"},
        })
        tgt = node_svc.create({
            "node_id": "TGT_LBL",
            "etikedoj": {"eo": "Homosapien", "fr": "Humain"},
        })

        merged = node_svc.merge_nodes(src["node_id"], tgt["node_id"])
        merged_lbls = json.loads(merged["etikedoj"])

        assert merged_lbls["eo"] == "Homosapien"
        assert merged_lbls["en"] == "Human"
        assert merged_lbls["fr"] == "Humain"

    def test_merge_same_node_raises(self, node_svc) -> None:
        """Merging a node into itself should raise ValueError."""
        node = node_svc.create({"node_id": "SAME", "etikedoj": {"eo": "Self"}})
        import pytest
        with pytest.raises(ValueError, match="different nodes"):
            node_svc.merge_nodes(node["node_id"], node["node_id"])

    def test_merge_nonexistent_source_raises(self, node_svc) -> None:
        """Merging with nonexistent source should raise ValueError."""
        tgt = node_svc.create({"node_id": "TGT_ONLY", "etikedoj": {"eo": "Only"}})
        import pytest
        with pytest.raises(ValueError, match="Source node not found"):
            node_svc.merge_nodes("NOEXIST_SRC", tgt["node_id"])

    def test_merge_nonexistent_target_raises(self, node_svc) -> None:
        """Merging with nonexistent target should raise ValueError."""
        src = node_svc.create({"node_id": "SRC_ONLY", "etikedoj": {"eo": "Only"}})
        import pytest
        with pytest.raises(ValueError, match="Target node not found"):
            node_svc.merge_nodes(src["node_id"], "NOEXIST_TGT")

    def test_merge_object_references(self, node_svc) -> None:
        """URI object references to source should be reassigned to target."""
        src = node_svc.create({"node_id": "OBJ_SRC", "etikedoj": {"eo": "ObjSrc"}})
        tgt = node_svc.create({"node_id": "OBJ_TGT", "etikedoj": {"eo": "ObjTgt"}})
        subj = node_svc.create({"node_id": "OBJ_SUBJ", "etikedoj": {"eo": "Subject"}})

        from A_semantika.service import get_predicate_service, get_triple_service

        pred_svc = get_predicate_service()
        triple_svc = get_triple_service()
        pred_svc.create({"predicate_id": "ex:likes"})
        triple_svc.add(subj["node_id"], "ex:likes", src["node_id"], "uri")

        assert triple_svc.count_by_subject_or_object(src["node_id"]) == 1

        node_svc.merge_nodes(src["node_id"], tgt["node_id"])

        triples = triple_svc.get_by_subject(subj["node_id"])
        assert len(triples) == 1
        assert triples[0]["object_value"] == tgt["node_id"]

    def test_merge_triple_pk_conflict_skipped(self, node_svc) -> None:
        """Triple PK conflicts should be silently skipped (target wins)."""
        src = node_svc.create({"node_id": "PK_SRC", "etikedoj": {"eo": "PkSrc"}})
        tgt = node_svc.create({"node_id": "PK_TGT", "etikedoj": {"eo": "PkTgt"}})
        obj = node_svc.create({"node_id": "PK_OBJ", "etikedoj": {"eo": "PkObj"}})

        from A_semantika.service import get_predicate_service, get_triple_service

        pred_svc = get_predicate_service()
        triple_svc = get_triple_service()
        pred_svc.create({"predicate_id": "ex:conflict"})

        triple_svc.add(src["node_id"], "ex:conflict", obj["node_id"], "uri")
        triple_svc.add(tgt["node_id"], "ex:conflict", obj["node_id"], "uri")

        assert triple_svc.count() == 2

        node_svc.merge_nodes(src["node_id"], tgt["node_id"])

        assert triple_svc.count() == 1
        triples = triple_svc.get_by_subject(tgt["node_id"])
        assert len(triples) == 1
        assert triples[0]["predicate_id"] == "ex:conflict"
        assert triples[0]["object_value"] == obj["node_id"]

    def test_merge_definitions(self, node_svc) -> None:
        """Definitions should merge with target-first precedence."""
        src = node_svc.create({
            "node_id": "DEF_SRC",
            "difinoj": {"eo": "Fonto-difino", "en": "Source definition"},
        })
        tgt = node_svc.create({
            "node_id": "DEF_TGT",
            "difinoj": {"eo": "Celo-difino", "fr": "Définition cible"},
        })

        merged = node_svc.merge_nodes(src["node_id"], tgt["node_id"])
        merged_defns = json.loads(merged["difinoj"])

        assert merged_defns["eo"] == "Celo-difino"
        assert merged_defns["en"] == "Source definition"
        assert merged_defns["fr"] == "Définition cible"

    def test_merge_update_target_timestamp(self, node_svc) -> None:
        """Target node's modifita_je should be updated after merge."""
        src = node_svc.create({"node_id": "TS_SRC", "etikedoj": {"eo": "TsSrc"}})
        tgt = node_svc.create({"node_id": "TS_TGT", "etikedoj": {"eo": "TsTgt"}})

        import time
        time.sleep(0.01)

        merged = node_svc.merge_nodes(src["node_id"], tgt["node_id"])
        assert merged["modifita_je"] > tgt["modifita_je"]
