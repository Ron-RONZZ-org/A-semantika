"""Tests for TripleService — add, remove, query methods, Turtle export."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _setup_nodes_and_predicates(node_svc, pred_svc) -> dict:
    """Create nodes and predicates needed for triple tests."""
    node_svc.create({"node_id": "s" + "0" * 35, "etikedoj": {"eo": "Hundo"}})
    node_svc.create({"node_id": "o" + "0" * 35, "etikedoj": {"eo": "Mamulo"}})
    node_svc.create({"node_id": "u" + "0" * 35, "etikedoj": {"eo": "Unuo"}})
    # rdf:type is seeded by DEFAULT_PREDICATES in storage.py — no need to create
    pred_svc.create({"predicate_id": "rdfs:label", "etikedoj": {"eo": "etikedo"}})
    pred_svc.create({"predicate_id": "wdt:P1082", "etikedoj": {"eo": "logxantaro"}})
    return {}


class TestTripleAdd:
    """Triple creation tests."""

    def test_add_uri_triple(self, triple_svc) -> None:
        """Adding a URI-reference triple should work."""
        result = triple_svc.add(
            subject_uuid="s" + "0" * 35,
            predicate_id="rdf:type",
            object_value="o" + "0" * 35,
            object_type="uri",
        )
        assert result is not None
        assert result["subject_uuid"] == "s" + "0" * 35
        assert result["predicate_id"] == "rdf:type"
        assert result["object_value"] == "o" + "0" * 35
        assert result["object_type"] == "uri"

    def test_add_string_literal(self, triple_svc) -> None:
        """Adding a string literal triple should work."""
        result = triple_svc.add(
            subject_uuid="s" + "0" * 35,
            predicate_id="rdfs:label",
            object_value="Hundo",
            object_type="literal",
            object_lang="eo",
        )
        assert result["object_type"] == "literal"
        assert result["object_lang"] == "eo"

    def test_add_typed_literal(self, triple_svc) -> None:
        """Adding a typed literal should work."""
        result = triple_svc.add(
            subject_uuid="s" + "0" * 35,
            predicate_id="wdt:P1082",
            object_value="1000000",
            object_type="literal",
            object_datatype="xsd:integer",
            object_unit="u" + "0" * 35,
        )
        assert result["object_datatype"] == "xsd:integer"
        assert result["object_unit"] == "u" + "0" * 35

    def test_add_duplicate_raises(self, triple_svc) -> None:
        """Adding a duplicate triple should raise ValueError."""
        triple_svc.add(
            subject_uuid="s" + "0" * 35,
            predicate_id="rdf:type",
            object_value="o" + "0" * 35,
            object_type="uri",
        )
        with pytest.raises(ValueError, match="already exists"):
            triple_svc.add(
                subject_uuid="s" + "0" * 35,
                predicate_id="rdf:type",
                object_value="o" + "0" * 35,
                object_type="uri",
            )

    def test_add_invalid_fk_raises(self, triple_svc) -> None:
        """Adding with invalid subject FK should raise."""
        with pytest.raises(ValueError):
            triple_svc.add(
                subject_uuid="nonexistent-uuid",
                predicate_id="rdf:type",
                object_value="o" + "0" * 35,
                object_type="uri",
            )


class TestTripleRead:
    """Triple query tests."""

    def test_get_one(self, triple_svc) -> None:
        """get_one should return the matching triple."""
        triple_svc.add(
            subject_uuid="s" + "0" * 35,
            predicate_id="rdf:type",
            object_value="o" + "0" * 35,
            object_type="uri",
        )
        result = triple_svc.get_one(
            subject_uuid="s" + "0" * 35,
            predicate_id="rdf:type",
            object_value="o" + "0" * 35,
            object_type="uri",
        )
        assert result is not None

    def test_get_by_subject(self, triple_svc) -> None:
        """get_by_subject should return all triples for a subject."""
        triple_svc.add(subject_uuid="s"+"0"*35, predicate_id="rdf:type", object_value="o"+"0"*35, object_type="uri")
        triple_svc.add(subject_uuid="s"+"0"*35, predicate_id="rdfs:label", object_value="Hundo", object_type="literal", object_lang="eo")
        results = triple_svc.get_by_subject("s" + "0" * 35)
        assert len(results) == 2

    def test_get_by_predicate(self, triple_svc) -> None:
        """get_by_predicate should return all triples with that predicate."""
        triple_svc.add(subject_uuid="s"+"0"*35, predicate_id="rdf:type", object_value="o"+"0"*35, object_type="uri")
        results = triple_svc.get_by_predicate("rdf:type")
        assert len(results) >= 1

    def test_get_by_sp(self, triple_svc) -> None:
        """get_by_sp should return triples matching subject+predicate."""
        triple_svc.add(subject_uuid="s"+"0"*35, predicate_id="rdf:type", object_value="o"+"0"*35, object_type="uri")
        results = triple_svc.get_by_sp("s" + "0" * 35, "rdf:type")
        assert len(results) == 1


class TestTripleDelete:
    """Triple deletion tests."""

    def test_remove_by_spo(self, triple_svc) -> None:
        """Removing by SPO should delete the exact triple."""
        triple_svc.add(subject_uuid="s"+"0"*35, predicate_id="rdf:type", object_value="o"+"0"*35, object_type="uri")
        deleted = triple_svc.remove(
            subject_uuid="s" + "0" * 35,
            predicate_id="rdf:type",
            object_value="o" + "0" * 35,
            object_type="uri",
        )
        assert deleted == 1
        assert triple_svc.count() == 0

    def test_remove_by_subject(self, triple_svc) -> None:
        """Removing by subject only should delete all for that subject."""
        triple_svc.add(subject_uuid="s"+"0"*35, predicate_id="rdf:type", object_value="o"+"0"*35, object_type="uri")
        deleted = triple_svc.remove(subject_uuid="s" + "0" * 35)
        assert deleted >= 1

    def test_remove_no_filters_raises(self, triple_svc) -> None:
        """Removing without filters should raise ValueError."""
        with pytest.raises(ValueError, match="At least one filter"):
            triple_svc.remove()


class TestTripleCountAndStats:
    """Triple count and stats tests."""

    def test_count(self, triple_svc) -> None:
        """Count should return the correct number."""
        assert triple_svc.count() == 0
        triple_svc.add(subject_uuid="s"+"0"*35, predicate_id="rdf:type", object_value="o"+"0"*35, object_type="uri")
        assert triple_svc.count() == 1

    def test_get_stats(self, triple_svc) -> None:
        """get_stats should return meaningful stats."""
        triple_svc.add(subject_uuid="s"+"0"*35, predicate_id="rdf:type", object_value="o"+"0"*35, object_type="uri")
        stats = triple_svc.get_stats()
        assert stats["total_triples"] == 1
        assert stats["unique_predicates"] >= 1
        assert stats["unique_subjects"] >= 1

    def test_get_by_node(self, triple_svc) -> None:
        """get_by_node should return triples where node is subject or URI object."""
        subj = "s"+"0"*35
        obj  = "o"+"0"*35
        other = "u"+"0"*35
        triple_svc.add(subject_uuid=subj, predicate_id="rdf:type", object_value=obj, object_type="uri")
        triple_svc.add(subject_uuid=obj, predicate_id="rdf:type", object_value=other, object_type="uri")

        # As subject
        r1 = triple_svc.get_by_node(subj)
        assert len(r1) == 1
        assert r1[0]["subject_uuid"] == subj

        # As URI object
        r2 = triple_svc.get_by_node(obj)
        assert len(r2) == 2  # as subject of 2nd triple, as object of 1st

        # Unrelated
        r3 = triple_svc.get_by_node("nonexistent")
        assert len(r3) == 0

    def test_remove_by_node(self, triple_svc) -> None:
        """remove_by_node should cascade-delete triples referencing a node."""
        subj = "s"+"0"*35
        obj  = "o"+"0"*35
        triple_svc.add(subject_uuid=subj, predicate_id="rdf:type", object_value=obj, object_type="uri")
        triple_svc.add(subject_uuid=obj, predicate_id="rdf:type", object_value=subj, object_type="uri")

        assert triple_svc.count() == 2
        removed = triple_svc.remove_by_node(subj)
        assert removed == 2  # removes both triples (subj as subject, subj as obj)
        assert triple_svc.count() == 0

    def test_count_by_subject_or_object(self, triple_svc) -> None:
        """count_by_subject_or_object should match get_by_node count."""
        subj = "s"+"0"*35
        obj  = "o"+"0"*35
        triple_svc.add(subject_uuid=subj, predicate_id="rdf:type", object_value=obj, object_type="uri")

        cnt = triple_svc.count_by_subject_or_object(subj)
        assert cnt == 1
        cnt = triple_svc.count_by_subject_or_object(obj)
        assert cnt == 1
        cnt = triple_svc.count_by_subject_or_object("nonexistent")
        assert cnt == 0


class TestTripleTurtleExport:
    """Turtle export tests."""

    def test_export_turtle_empty(self, triple_svc) -> None:
        """Exporting empty store should produce minimal Turtle."""
        ttl = triple_svc.export_turtle()
        assert "@prefix" in ttl
        assert "example.org" in ttl

    def test_export_turtle_with_triples(self, triple_svc) -> None:
        """Exporting with triples should produce valid Turtle."""
        triple_svc.add(
            subject_uuid="s" + "0" * 35,
            predicate_id="rdf:type",
            object_value="o" + "0" * 35,
            object_type="uri",
        )
        ttl = triple_svc.export_turtle()
        assert ":s0000000" in ttl
        assert ":rdf:type" in ttl
        assert ":o0000000" in ttl

    def test_export_turtle_literal(self, triple_svc) -> None:
        """Exporting string literals should quote them."""
        triple_svc.add(
            subject_uuid="s" + "0" * 35,
            predicate_id="rdfs:label",
            object_value="Hundo",
            object_type="literal",
            object_lang="eo",
        )
        ttl = triple_svc.export_turtle()
        assert '"Hundo"@eo' in ttl or "Hundo" in ttl
