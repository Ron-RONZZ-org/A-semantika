"""FTS5 query sanitization edge cases.

Extracted from test_edge_cases.py — TestFTS5Sanitization.
"""
from __future__ import annotations


class TestFTS5Sanitization:
    """FTS5 query sanitization should resist injection (M1)."""

    def test_search_with_special_chars(self, node_svc):
        """Special FTS5 chars should not crash search."""
        node_svc.create({"etikedoj": {"eo": "Testo-normala"}})

        # Various FTS5 special chars that previously could crash
        for query in [
            '" OR 1=1 --',
            '*',
            '^',
            '-',
            '+',
            '~',
            '(',
            ')',
            '{',
            '}',
            '[',
            ']',
            ':',
            '<',
            '>',
            '%',
            'a"b',
            'a*b',
            'a^b',
            'a-b',
            'a+b',
            'a~b',
        ]:
            # Should not raise fts5 syntax error
            results = node_svc.search(query)
            assert results is not None, f"Search with '{query}' returned None"

    def test_search_pure_special_chars(self, node_svc):
        """Pure special char queries should return all (sanitized to empty)."""
        node_svc.create({"etikedoj": {"eo": "Testo-123"}})
        # Query made entirely of special chars → sanitized to empty → list all
        results = node_svc.search("***^^^---")
        assert results is not None

    def test_search_mixed_special_and_normal(self, node_svc):
        """Normal text mixed with special chars should still match."""
        node_svc.create({"etikedoj": {"eo": "Esperanta Teksto"}})
        results = node_svc.search("Esperanta***^^^")
        assert len(results) >= 1

    def test_search_with_and_keyword(self, node_svc):
        """FTS5 keyword 'AND' should be treated as a regular content term."""
        node_svc.create({"etikedoj": {"eo": "A AND B"}})
        # "AND" should not be stripped — search should find the node
        results = node_svc.search("AND")
        assert len(results) >= 1
        # Multi-token with AND keyword
        results = node_svc.search("A AND B")
        assert len(results) >= 1

    def test_search_with_or_keyword(self, node_svc):
        """FTS5 keyword 'OR' should be treated as a regular content term."""
        node_svc.create({"etikedoj": {"eo": "One OR Two"}})
        results = node_svc.search("OR")
        assert len(results) >= 1

    def test_search_with_not_keyword(self, node_svc):
        """FTS5 keyword 'NOT' should be treated as a regular content term."""
        node_svc.create({"etikedoj": {"eo": "Do NOT do this"}})
        results = node_svc.search("NOT")
        assert len(results) >= 1

    def test_search_keyword_does_not_affect_normal_search(self, node_svc):
        """FTS5 keyword lowercasing should not break normal searches."""
        node_svc.create({"etikedoj": {"eo": "Normal search term"}})
        results = node_svc.search("Normal")
        assert len(results) >= 1

    def test_search_with_dot_in_label_prefix(self, node_svc):
        """Words with trailing dots (e.g. 'L.' in 'John L. Holland') must not crash FTS5."""
        node_svc.create({"etikedoj": {"en": "John L. Holland"}})
        # This was crashing with "fts5: syntax error near ." because
        # 'L.' was kept in the FTS5 token and 'L.*' was interpreted
        # as column-prefix syntax.
        results = node_svc.search("John L. Holland", limit=1)
        assert len(results) >= 1
        assert results[0]["label_text"] == "John L. Holland"

    def test_search_predicate_with_dot(self, pred_svc):
        """Predicate FTS5 search should also handle dots gracefully."""
        pred_svc.create({"predicate_id": "test:dot", "etikedoj": '{"en": "Dr. Smith"}'})
        results = pred_svc.search("Dr. Smith", limit=1)
        assert len(results) >= 1
