"""Confirmation preview: Rich table builder + label resolution for triples.

This is a **re-export facade** — all implementations live in specialized
sub-modules that were extracted during the 500-line monolith split:

- ``_preview_helpers.py`` — ``resolve_node_label``, ``resolve_predicate_label``
- ``_preview_triple.py`` — ``build_triple_preview_table``, ``confirm_triple``
- ``_preview_node.py`` — node preview, node creation confirmation
- ``_preview_predicate.py`` — predicate preview, predicate creation confirmation

All public symbols are re-exported here for backward compatibility.
New code should continue importing from ``_preview`` (the facade).
"""
from __future__ import annotations

from A_semantika._preview_helpers import (
    resolve_node_label,
    resolve_node_label_from_node,
    resolve_predicate_label,
)
from A_semantika._preview_triple import (
    build_metadata_diff_table,
    build_triple_preview_table,
    confirm_triple,
)
from A_semantika._preview_node import (
    build_node_modify_preview,
    build_node_preview_table,
    confirm_node_creation,
    confirm_node_with_arcs,
)
from A_semantika._preview_predicate import (
    build_predicate_modify_preview,
    build_predicate_preview_table,
    confirm_predicate_creation,
)

__all__ = [
    "build_node_modify_preview",
    "build_node_preview_table",
    "build_predicate_modify_preview",
    "build_predicate_preview_table",
    "build_triple_preview_table",
    "confirm_node_creation",
    "confirm_node_with_arcs",
    "confirm_predicate_creation",
    "confirm_triple",
    "resolve_node_label",
    "resolve_node_label_from_node",
    "resolve_predicate_label",
]
