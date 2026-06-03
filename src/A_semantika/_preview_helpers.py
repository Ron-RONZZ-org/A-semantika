"""Label resolution helpers for Rich table previews.

Extracted from ``_preview.py`` during the 500-line monolith split.
Provides display-label resolution for nodes and predicates used by
all preview tables.
"""

from __future__ import annotations

from A_semantika._node_helpers import AmbiguousUUIDError, get_display_label, get_label_from_node, truncate_uuid
from A_semantika._node_service import NodeService
from A_semantika._predicate_service import PredicateService
from A_semantika.data.storage import label_from_json


def resolve_node_label(node_svc: NodeService, uuid_or_prefix: str, preferred_lang: str | None = None) -> str:
    """Resolve a node UUID/prefix to a display label.

    Delegates to ``get_display_label()`` from ``_node_helpers`` to avoid
    duplicating the label fallback logic.

    Args:
        node_svc: NodeService instance.
        uuid_or_prefix: Node ID or prefix.
        preferred_lang: Optional language code to try first
            (defaults to ``eo -> en -> first`` fallback).

    Returns the label if found, the UUID prefix as fallback.

    Raises:
        AmbiguousUUIDError: If the prefix matches multiple nodes.
    """
    try:
        label, _ = get_display_label(node_svc.resolve_node_id_prefix, uuid_or_prefix, preferred_lang)
        return label
    except AmbiguousUUIDError:
        raise
    except ValueError:
        return truncate_uuid(uuid_or_prefix)


def resolve_node_label_from_node(node: dict, preferred_lang: str | None = None) -> str:
    """Get display label from a pre-resolved node dict.

    Avoids redundant ``node_svc.resolve_node_id_prefix()`` calls when the
    node dict has already been fetched (e.g. in ``build_triple_preview_table()``).

    Delegates to :func:`get_label_from_node` to share the same label
    fallback logic as :func:`resolve_node_label`.

    Args:
        node: Pre-resolved node dict.
        preferred_lang: Optional language code to try first.
    """
    return get_label_from_node(node, preferred_lang=preferred_lang)


def resolve_predicate_label(pred_svc: PredicateService, predicate_id: str, preferred_lang: str | None = None) -> str:
    """Resolve a predicate ID to a display label.

    Returns label in the preferred language (if given), otherwise
    ``eo -> en -> first`` fallback.  Falls back to predicate_id if no label
    is available.  Delegates to storage.label_from_json().

    Args:
        pred_svc: PredicateService instance.
        predicate_id: Predicate ID.
        preferred_lang: Optional language code to try first.
    """
    pred = pred_svc.get_by_predicate_id(predicate_id)
    if not pred:
        return predicate_id
    etikedoj = pred.get("etikedoj", "{}")
    lang_fallback = (preferred_lang, "eo", "en") if preferred_lang else ("eo", "en")
    label = label_from_json(etikedoj, lang_fallback)
    return label if label else predicate_id
