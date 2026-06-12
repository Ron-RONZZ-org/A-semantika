"""Reczeni helpers — session management, distractor generation, review logic.

Extracted to keep _recenzi_cmd.py under 500 lines.
"""
from __future__ import annotations

import uuid as uuid_mod
from typing import TYPE_CHECKING, Any

from A_semantika.data.storage import get_db, now

if TYPE_CHECKING:
    from A_semantika._node_service import NodeService
    from A_semantika._predicate_service import PredicateService
    from A_semantika._triple_service import TripleService


# ── Session CRUD ─────────────────────────────────────────────────────────────


def create_session(
    modo: str,
    dato_de: str | None = None,
    dato_gis: str | None = None,
) -> dict:
    """Create a new review session.

    Returns:
        The created session dict with uuid, modo, etc.
    """
    db = get_db()
    sesio_uuid = str(uuid_mod.uuid4())
    timestamp = now()
    db.execute(
        "INSERT INTO recenzo_sesio (uuid, modo, dato_de, dato_gis, totalo, korekta, finita, kreita_je) "
        "VALUES (?, ?, ?, ?, 0, 0, 0, ?)",
        (sesio_uuid, modo, dato_de, dato_gis, timestamp),
    )
    return {
        "uuid": sesio_uuid,
        "modo": modo,
        "dato_de": dato_de,
        "dato_gis": dato_gis,
        "totalo": 0,
        "korekta": 0,
        "finita": 0,
        "kreita_je": timestamp,
    }


def get_session(sesio_uuid: str) -> dict | None:
    """Get a session by UUID."""
    return get_db().execute_one(
        "SELECT * FROM recenzo_sesio WHERE uuid = ?", (sesio_uuid,)
    )


def list_sessions(limit: int = 20) -> list[dict]:
    """List past review sessions, most recent first."""
    return get_db().execute(
        "SELECT * FROM recenzo_sesio ORDER BY kreita_je DESC LIMIT ?", (limit,)
    )


def update_session_score(sesio_uuid: str, korekta: int, totalo: int) -> None:
    """Update score for a session."""
    get_db().execute(
        "UPDATE recenzo_sesio SET korekta = ?, totalo = ? WHERE uuid = ?",
        (korekta, totalo, sesio_uuid),
    )


def finish_session(sesio_uuid: str) -> None:
    """Mark a session as finished."""
    get_db().execute(
        "UPDATE recenzo_sesio SET finita = 1 WHERE uuid = ?", (sesio_uuid,)
    )


def delete_session(sesio_uuid: str) -> bool:
    """Delete a session and its results.

    Returns:
        True if the session existed and was deleted.
    """
    db = get_db()
    # Check existence first since execute() returns list[dict] not cursor
    existing = db.execute_one(
        "SELECT uuid FROM recenzo_sesio WHERE uuid = ?", (sesio_uuid,)
    )
    if not existing:
        return False
    db.execute("DELETE FROM recenzo_rezulto WHERE sesio_uuid = ?", (sesio_uuid,))
    db.execute("DELETE FROM recenzo_sesio WHERE uuid = ?", (sesio_uuid,))
    return True


# ── Result CRUD ──────────────────────────────────────────────────────────────


def add_result(
    sesio_uuid: str,
    subject_uuid: str,
    predicate_id: str,
    object_value: str,
    object_type: str,
    korekta: bool,
    respondo: str | None,
    pozicio: int,
) -> dict:
    """Add a single result entry to a session."""
    db = get_db()
    res_uuid = str(uuid_mod.uuid4())
    timestamp = now()
    db.execute(
        "INSERT INTO recenzo_rezulto "
        "(uuid, sesio_uuid, subject_uuid, predicate_id, object_value, "
        " object_type, korekta, respondo, pozicio, kreita_je) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (res_uuid, sesio_uuid, subject_uuid, predicate_id, object_value,
         object_type, 1 if korekta else 0, respondo, pozicio, timestamp),
    )
    return {
        "uuid": res_uuid,
        "sesio_uuid": sesio_uuid,
        "subject_uuid": subject_uuid,
        "predicate_id": predicate_id,
        "object_value": object_value,
        "object_type": object_type,
        "korekta": korekta,
        "respondo": respondo,
        "pozicio": pozicio,
        "kreita_je": timestamp,
    }


def get_results(sesio_uuid: str) -> list[dict]:
    """Get all results for a session, ordered by position."""
    return get_db().execute(
        "SELECT * FROM recenzo_rezulto WHERE sesio_uuid = ? ORDER BY pozicio",
        (sesio_uuid,),
    )


# ── Triple queries for review ────────────────────────────────────────────────


def get_triples_for_review(
    triple_svc: TripleService,
    dato_de: str | None = None,
    dato_gis: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Fetch triples within a date range for review.

    Uses search_triples with ``1=1`` WHERE clause and optional date filters.
    Randomises the result order so the user sees a shuffled selection.
    """
    import random

    fetch_limit = limit * 3
    results = triple_svc.search_triples(
        "1=1", [], limit=fetch_limit,
        dato_de=dato_de, dato_gis=dato_gis,
    )
    random.shuffle(results)
    return results[:limit]


# ── Distractor generation ────────────────────────────────────────────────────


def generate_distractors(
    correct_object_value: str,
    correct_object_type: str,
    node_svc: NodeService,
    pred_svc: PredicateService,
    triple_svc: TripleService,
    count: int = 3,
) -> list[str]:
    """Generate distractor object values for multiple-choice review.

    For URI objects, finds other nodes with similar labels via FTS5.
    For literal objects, finds other literal values via LIKE on the
    triple store.

    Args:
        correct_object_value: The correct object value (node_id or literal).
        correct_object_type: 'uri' or 'literal'.
        node_svc: NodeService instance.
        pred_svc: PredicateService instance.
        triple_svc: TripleService instance.
        count: Number of distractors to generate.

    Returns:
        List of distractor strings (may be shorter than *count* if
        insufficient candidates exist).
    """
    distractors: list[str] = []

    if correct_object_type == "uri":
        candidate = node_svc.get(correct_object_value)
        if candidate:
            labels = candidate.get("etikedoj", "{}")
            import json
            try:
                labels_dict = json.loads(labels) if isinstance(labels, str) else labels
            except (json.JSONDecodeError, TypeError):
                labels_dict = {}
            label_text = next(
                (v for v in labels_dict.values() if isinstance(v, str) and v),
                None,
            )
            if label_text and len(label_text) >= 2:
                related = node_svc.search(label_text, limit=count + 5)
                for r in related:
                    if r["node_id"] != correct_object_value and r["node_id"] not in distractors:
                        distractors.append(r["node_id"])
                    if len(distractors) >= count:
                        break
    else:
        escaped = correct_object_value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if len(escaped) >= 2:
            similar = triple_svc.search_triples(
                "object_type = 'literal' AND object_value LIKE ? ESCAPE '\\'",
                [f"%{escaped[:10]}%"],
                limit=count + 5,
            )
            for t in similar:
                val = t["object_value"]
                if val != correct_object_value and val not in distractors:
                    distractors.append(val)
                if len(distractors) >= count:
                        break

    return distractors[:count]


def build_question_data(
    triple: dict,
    node_svc: NodeService,
    pred_svc: PredicateService,
    triple_svc: TripleService,
    mode: str,
) -> dict:
    """Build a question dict from a triple.

    Args:
        triple: A triple dict from the database.
        node_svc: NodeService instance.
        pred_svc: PredicateService instance.
        triple_svc: TripleService instance.
        mode: 'rigardi' or 'multobla'.

    Returns:
        Question dict with keys: subject_label, predicate_label,
        object_value, object_type, object_display, and
        options (for multobla mode).
    """
    from A_semantika._preview import resolve_node_label, resolve_predicate_label

    subj_label = resolve_node_label(node_svc, triple["subject_uuid"])
    pred_label = resolve_predicate_label(pred_svc, triple["predicate_id"])

    obj_display: str
    if triple["object_type"] == "uri":
        obj_display = resolve_node_label(node_svc, triple["object_value"])
    else:
        obj_display = triple["object_value"]

    result: dict[str, Any] = {
        "subject_uuid": triple["subject_uuid"],
        "predicate_id": triple["predicate_id"],
        "object_value": triple["object_value"],
        "object_type": triple["object_type"],
        "subject_label": subj_label,
        "predicate_label": pred_label,
        "object_display": obj_display,
    }

    if mode == "multobla":
        distractors = generate_distractors(
            triple["object_value"],
            triple["object_type"],
            node_svc,
            pred_svc,
            triple_svc,
            count=3,
        )
        options = [triple["object_value"]] + distractors
        import random
        random.shuffle(options)
        result["options"] = options

    return result
