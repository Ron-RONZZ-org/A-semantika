"""Performance benchmarks for bulk operations in A-semantika.

Benchmarks measure:
1. Bulk triple queries (TripleService.get_by_nodes) vs. looping get_by_node()
2. Bulk node deletion with triple cleanup
3. FTS5 search performance on large datasets
4. Conditional FTS rebuild (Issue #40 F1)

These are informational only — not part of the standard test suite.
Run with: python -m pytest tests/test_perf_benchmarks.py -v -s
"""

import time
from typing import Any

import pytest

from A_semantika.service import (
    get_node_service,
    get_predicate_service,
    get_triple_service,
)
from A_semantika.data.storage import get_db


@pytest.mark.benchmark
class TestBulkTripleQueries:
    """Benchmark bulk triple queries vs. looping single queries."""

    def test_get_by_nodes_bulk_vs_loop_10_nodes(self) -> None:
        """Compare O(1) bulk query vs. O(N) loop: 10 nodes."""
        node_svc = get_node_service()
        triple_svc = get_triple_service()
        pred_svc = get_predicate_service()

        # Setup: Create 10 nodes and 50 triples
        nodes = []
        for i in range(10):
            node = node_svc.create({
                "node_id": f"BENCH_NODE_{i}",
                "etikedoj": {"eo": f"Nodo {i}", "en": f"Node {i}"},
            })
            nodes.append(node)

        # Create 5 triples per node
        for node in nodes:
            for j in range(5):
                triple_svc.add(
                    subject_uuid=node["node_id"],
                    predicate_id="rdf:type",
                    object_value=f"TYPE_{j}",
                    object_type="literal",
                )

        # Benchmark: bulk query
        start = time.perf_counter()
        bulk_results = triple_svc.get_by_nodes([n["node_id"] for n in nodes])
        bulk_time = time.perf_counter() - start

        # Benchmark: loop query
        start = time.perf_counter()
        loop_results = []
        for node in nodes:
            loop_results.extend(triple_svc.get_by_node(node["node_id"]))
        loop_time = time.perf_counter() - start

        # Both should return same count
        assert len(bulk_results) == len(loop_results) == 50

        # Bulk should be faster (or comparable on small dataset)
        speedup = loop_time / bulk_time if bulk_time > 0 else 1.0
        print(f"\nBulk query: {bulk_time*1000:.2f}ms, Loop query: {loop_time*1000:.2f}ms, Speedup: {speedup:.1f}x")

    def test_get_by_nodes_bulk_vs_loop_100_nodes(self) -> None:
        """Compare O(1) bulk query vs. O(N) loop: 100 nodes."""
        node_svc = get_node_service()
        triple_svc = get_triple_service()

        # Setup: Create 100 nodes and 500 triples
        nodes = []
        for i in range(100):
            node = node_svc.create({
                "node_id": f"BENCH_NODE_100_{i}",
                "etikedoj": {"eo": f"Nodo {i}"},
            })
            nodes.append(node)

        for node in nodes:
            triple_svc.add(
                subject_uuid=node["node_id"],
                predicate_id="rdf:type",
                object_value="TYPE_X",
                object_type="literal",
            )

        # Benchmark: bulk query
        start = time.perf_counter()
        bulk_results = triple_svc.get_by_nodes([n["node_id"] for n in nodes])
        bulk_time = time.perf_counter() - start

        # Benchmark: loop query
        start = time.perf_counter()
        loop_results = []
        for node in nodes:
            loop_results.extend(triple_svc.get_by_node(node["node_id"]))
        loop_time = time.perf_counter() - start

        assert len(bulk_results) == len(loop_results) == 100
        speedup = loop_time / bulk_time if bulk_time > 0 else 1.0
        print(f"\nBulk query (100 nodes): {bulk_time*1000:.2f}ms, Loop query: {loop_time*1000:.2f}ms, Speedup: {speedup:.1f}x")


@pytest.mark.benchmark
class TestFTSPerformance:
    """Benchmark FTS5 search performance."""

    def test_fts5_search_100_nodes_with_labels(self) -> None:
        """Measure FTS5 search speed with 100 labeled nodes."""
        node_svc = get_node_service()

        # Setup: Create 100 nodes with multilingual labels
        labels = ["Kato", "Hundo", "Birdo", "Pesco", "Serpento", "Insekto"]
        for i in range(100):
            label = labels[i % len(labels)]
            node_svc.create({
                "node_id": f"FTS_NODE_{i}",
                "etikedoj": {"eo": f"{label} {i}", "en": f"{label.lower()} {i}"},
            })

        # Benchmark: FTS5 search
        start = time.perf_counter()
        results = node_svc.search("Kato", limit=100)
        search_time = time.perf_counter() - start

        assert len(results) > 0
        print(f"\nFTS5 search 'Kato' in 100 nodes: {search_time*1000:.2f}ms, {len(results)} results")

    def test_fts5_search_with_special_chars(self) -> None:
        """Measure FTS5 search with special characters (edge case)."""
        node_svc = get_node_service()

        # Create nodes with special chars that are FTS5 keywords
        keywords = ["AND", "OR", "NOT", "NEAR", "COLUMN"]
        for i, kw in enumerate(keywords * 10):  # 50 nodes
            node_svc.create({
                "node_id": f"KEYWORD_NODE_{i}",
                "etikedoj": {"eo": f"{kw} testo {i}"},
            })

        # Benchmark: search for keyword
        start = time.perf_counter()
        results = node_svc.search("AND", limit=100)
        search_time = time.perf_counter() - start

        print(f"\nFTS5 search 'AND' (FTS5 keyword) in 50 nodes: {search_time*1000:.2f}ms, {len(results)} results")


@pytest.mark.benchmark
class TestConditionalFTSRebuild:
    """Benchmark conditional FTS rebuild (Issue #40 F1)."""

    def test_init_db_no_rebuild_on_second_call(self) -> None:
        """Measure init_db performance when FTS rebuild is skipped."""
        from A_semantika.data.storage import init_db

        db = get_db()

        # First call: full initialization (includes seed + rebuild)
        start = time.perf_counter()
        init_db(db)
        first_call_time = time.perf_counter() - start

        # Second call: should skip rebuild (all predicates exist)
        start = time.perf_counter()
        init_db(db)
        second_call_time = time.perf_counter() - start

        # Second call should be much faster (no FTS rebuild)
        print(f"\nFirst init_db() call: {first_call_time*1000:.2f}ms")
        print(f"Second init_db() call: {second_call_time*1000:.2f}ms")
        print(f"Speedup: {first_call_time / second_call_time if second_call_time > 0 else 1.0:.1f}x")


@pytest.mark.benchmark
class TestNodeDeletionWithCleanup:
    """Benchmark node deletion with triple cleanup."""

    def test_delete_node_with_many_triples(self) -> None:
        """Measure deletion of a node with 100 outgoing triples."""
        node_svc = get_node_service()
        triple_svc = get_triple_service()

        # Setup: Create a node with 100 outgoing triples
        source_node = node_svc.create({
            "node_id": "SOURCE_NODE",
            "etikedoj": {"eo": "Fonto"},
        })

        for i in range(100):
            # Create a target node for each triple
            target_node = node_svc.create({
                "node_id": f"TARGET_NODE_{i}",
                "etikedoj": {"eo": f"Celo {i}"},
            })
            triple_svc.add(
                subject_uuid=source_node["node_id"],
                predicate_id="rdf:type",
                object_value=target_node["node_id"],
                object_type="uri",
            )

        # Benchmark: delete the source node with its triples
        # First, remove triples (simulating what CLI does)
        start = time.perf_counter()
        triple_svc.remove_by_node(source_node["node_id"])
        node_svc.delete(source_node["node_id"])
        delete_time = time.perf_counter() - start

        # Verify deletion
        assert node_svc.get(source_node["node_id"]) is None

        print(f"\nDelete node with 100 outgoing triples: {delete_time*1000:.2f}ms")

    def test_bulk_delete_nodes_via_service(self) -> None:
        """Measure bulk deletion of 50 nodes."""
        node_svc = get_node_service()

        # Create 50 nodes
        nodes = []
        for i in range(50):
            node = node_svc.create({
                "node_id": f"BULK_DELETE_NODE_{i}",
                "etikedoj": {"eo": f"Nodo {i}"},
            })
            nodes.append(node)

        # Benchmark: delete all nodes
        start = time.perf_counter()
        for node in nodes:
            node_svc.delete(node["node_id"])
        delete_time = time.perf_counter() - start

        print(f"\nBulk delete 50 nodes: {delete_time*1000:.2f}ms, {delete_time/50*1000:.2f}ms per node")
