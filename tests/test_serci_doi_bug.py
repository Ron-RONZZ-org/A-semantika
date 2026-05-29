"""Regression test: serci with non-hex node IDs (DOI pattern) must find triples."""
import pytest


@pytest.fixture(autouse=True)
def _setup_nodes_and_predicates(node_svc, pred_svc) -> None:
    """Create nodes with DOI-like node IDs (non-hex, with underscores)."""
    node_svc.create({"node_id": "H_WMCCULLOCH", "etikedoj": {"eo": "Warren McCulloch"}})
    node_svc.create({"node_id": "H_WPITTS",     "etikedoj": {"eo": "Walter Pitts"}})
    node_svc.create({"node_id": "DOI_10_1007_BF02", "etikedoj": {"eo": "A Logical Calculus"}})
    pred_svc.create({"predicate_id": "estas_autor_de", "etikedoj": {"eo": "estas aŭtoro de"}})


@pytest.fixture
def _with_triples(triple_svc) -> None:
    """Create triples where DOI is the object (URI reference)."""
    triple_svc.add(
        subject_uuid="H_WMCCULLOCH",
        predicate_id="estas_autor_de",
        object_value="DOI_10_1007_BF02",
        object_type="uri",
    )
    triple_svc.add(
        subject_uuid="H_WPITTS",
        predicate_id="estas_autor_de",
        object_value="DOI_10_1007_BF02",
        object_type="uri",
    )


class TestSerciDOI:
    def test_resolve_subjects_finds_node(self, node_svc):
        from A_semantika._triple_search import resolve_subjects
        subjs = resolve_subjects(node_svc, "DOI_10_1007_BF02")
        assert subjs == ["DOI_10_1007_BF02"], f"Expected ['DOI_10_1007_BF02'], got {subjs}"

    def test_resolve_objects_finds_node(self, node_svc):
        from A_semantika._triple_search import resolve_objects
        obj_uuids, obj_lits = resolve_objects(node_svc, "DOI_10_1007_BF02")
        assert obj_uuids == ["DOI_10_1007_BF02"], f"Expected ['DOI_10_1007_BF02'], got {obj_uuids}"
        assert obj_lits == [], f"Expected [], got {obj_lits}"

    def test_search_triples_any_field_finds_triples(self, node_svc, pred_svc, triple_svc, _with_triples):
        from A_semantika._triple_search import search_triples_any_field
        results = search_triples_any_field(
            triple_svc=triple_svc,
            node_svc=node_svc,
            pred_svc=pred_svc,
            search_term="DOI_10_1007_BF02",
            limit=50,
        )
        assert len(results) == 2, f"Expected 2 triples, got {len(results)}"
        for r in results:
            assert r["object_value"] == "DOI_10_1007_BF02"
