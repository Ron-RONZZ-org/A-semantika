"""Turtle (.ttl) export for Triples.

Extracted from _triple_service.py to keep that file under 500 lines.

Emits rdfs:label triples for node labels (from etikedoj JSON) in standard
RDF Turtle format — follows the W3C RDFS recommendation for label
annotation of resources.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Turtle PN_LOCAL (simplified): chars allowed in prefixed-name local part.
# Must NOT start with a digit.
_PN_LOCAL_RE: re.Pattern = re.compile(
    r"^[a-zA-Z_\u0080-\uffff][a-zA-Z0-9_\u0080-\uffff\-.]*$"
)


def _escape_turtle_literal(val: str) -> str:
    """Escape a literal value for Turtle output.

    Escapes backslash, double quote, newline, carriage return, and tab.
    """
    val = val.replace("\\", "\\\\")
    val = val.replace('"', '\\"')
    val = val.replace("\n", "\\n")
    val = val.replace("\r", "\\r")
    val = val.replace("\t", "\\t")
    return val


def _format_turtle_uri(val: str, prefix_uris: dict[str, str], base_uri: str) -> str:
    """Format a URI reference for Turtle, respecting known namespaces.

    Known prefixes (rdf:, rdfs:, xsd:, owl:) are emitted as prefixed names.
    For unknown prefixes (e.g. wdt:P1082 when wdt is not in prefix_uris),
    the full value is wrapped in ``<...>`` to preserve its identity.
    For values without a colon, the local part must be a valid Turtle
    PN_LOCAL (not start with a digit); otherwise a full ``<...>`` URI
    using *base_uri* is emitted.

    Args:
        val: The URI reference string.
        prefix_uris: Mapping of prefix to namespace URI (e.g. {"rdf": "http://..."}).
        base_uri: The base URI for the default namespace (used for full URIs
                  when the value cannot be expressed as a prefixed name).

    Returns:
        A Turtle-compatible URI string (prefixed name or full URI in <...>).
    """
    if ":" in val:
        prefix, _, local = val.partition(":")
        if prefix in prefix_uris:
            if _PN_LOCAL_RE.match(local):
                return val  # Known prefix, valid local part -> prefixed name
            # Known prefix but invalid local part (e.g. starts with digit)
            # -> expand to full URI
            return f"<{prefix_uris[prefix]}{local}>"
        # Unknown prefix - emit as full URI preserving identity
        return f"<{val}>"
    # No colon in val
    if _PN_LOCAL_RE.match(val):
        return f":{val}"
    # Fall back to full URI with base
    return f"<{base_uri}{val}>"


def _build_label_map(db: Any) -> dict[str, list[tuple[str, str]]]:
    """Build a map of node_id -> list of (label_value, lang_code).

    Parses etikedoj JSON from all nodes. Returns only nodes that have
    at least one non-empty label.

    Args:
        db: Database instance (SQLiteDB or compatible).

    Returns:
        Dict mapping node_id to a list of (value, lang) tuples.
    """
    label_map: dict[str, list[tuple[str, str]]] = {}
    rows = db.execute("SELECT node_id, etikedoj FROM nodes")
    for row in rows:
        try:
            raw = json.loads(row["etikedoj"]) if isinstance(row["etikedoj"], str) else row["etikedoj"]
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(raw, dict):
            continue
        pairs: list[tuple[str, str]] = []
        for lang, val in raw.items():
            if val and isinstance(val, str):
                pairs.append((val, lang))
        if pairs:
            label_map[row["node_id"]] = pairs
    return label_map


def _append_label_lines(
    subject_lines: list[str],
    node_id: str,
    label_map: dict[str, list[tuple[str, str]]],
    indent: str = "    ",
) -> None:
    """Append rdfs:label lines for a node to the subject_lines buffer.

    Turtle syntax for multiple language-tagged labels on the same predicate
    uses comma separation:

        rdfs:label "Spaco"@eo ,
                   "Space"@en ;

    If there are no labels for *node_id*, the buffer is unchanged.

    Args:
        subject_lines: Mutable list of Turtle lines for the current subject.
        node_id: The node to look up labels for.
        label_map: Map built by :func:`_build_label_map`.
        indent: Indentation string for predicate lines.
    """
    pairs = label_map.get(node_id)
    if not pairs:
        return

    parts: list[str] = []
    for val, lang in pairs:
        escaped = _escape_turtle_literal(val)
        if lang:
            parts.append(f'"{escaped}"@{lang}')
        else:
            parts.append(f'"{escaped}"')

    if len(parts) == 1:
        subject_lines.append(f"{indent}rdfs:label {parts[0]};")
    else:
        subject_lines.append(f"{indent}rdfs:label {parts[0]},")
        for part in parts[1:-1]:
            subject_lines.append(f"{indent}           {part},")
        subject_lines.append(f"{indent}           {parts[-1]};")


def export_turtle(
    db: Any,
    prefix_uris: dict[str, str],
    base_uri: str = "https://example.org/",
) -> str:
    """Export all triples to Turtle (.ttl) format.

    Triples are grouped by subject, with predicates formatted as::

      subject
          predicate1 object1 ;
          predicate2 object2 ;
          predicate3 object3 .

    Each node's labels (stored in ``etikedoj`` JSON) are emitted as
    standard ``rdfs:label`` triples with language tags.  Nodes that have
    no outgoing triples appear as nodes with only ``rdfs:label`` (instead
    of the old comment format).  Nodes with neither triples nor labels
    are silently omitted.

    Args:
        db: Database instance (SQLiteDB or compatible).
        prefix_uris: Mapping of prefix to namespace URI.
        base_uri: Base URI for node references.

    Returns:
        Turtle formatted string.
    """
    lines = [
        "@prefix : <{base}> .".format(base=base_uri),
    ]
    for prefix, uri in sorted(prefix_uris.items()):
        lines.append(f"@prefix {prefix}: <{uri}> .")
    lines.append("")

    # Pre-build label map for rdfs:label emission
    label_map = _build_label_map(db)

    triples = db.execute(
        """SELECT t.*, p.etikedoj AS pred_etikedoj
           FROM triples t
           JOIN nodes n ON t.subject_uuid = n.node_id
           JOIN predicates p ON t.predicate_id = p.predicate_id
           ORDER BY t.subject_uuid, t.predicate_id"""
    )

    current_subject = None
    subject_lines: list[str] = []
    subjects_with_triples: set[str] = set()

    for t in triples:
        subj_uri = _format_turtle_uri(t["subject_uuid"], prefix_uris, base_uri)
        pred_uri = _format_turtle_uri(t["predicate_id"], prefix_uris, base_uri)
        subjects_with_triples.add(t["subject_uuid"])

        if t["object_type"] == "uri":
            obj = _format_turtle_uri(t["object_value"], prefix_uris, base_uri)
        elif t["object_datatype"]:
            # Typed literal - handle custom datatypes, not only xsd:
            escaped_val = _escape_turtle_literal(t["object_value"])
            dtype = t["object_datatype"]
            if ":" in dtype:
                ns, _, local = dtype.partition(":")
                if ns == "xsd":
                    obj = f'"{escaped_val}"^^xsd:{local}'
                else:
                    # Custom datatype - emit full URI or prefixed form
                    obj = f'"{escaped_val}"^^<{dtype}>'
            else:
                obj = f'"{escaped_val}"^^<{dtype}>'
        elif t["object_lang"]:
            escaped_val = _escape_turtle_literal(t["object_value"])
            obj = f'"{escaped_val}"@{t["object_lang"]}'
        else:
            escaped_val = _escape_turtle_literal(t["object_value"])
            obj = f'"{escaped_val}"'

        # Subject changed: flush previous subject's triples
        if t["subject_uuid"] != current_subject:
            if subject_lines:
                # Append rdfs:label for the previous subject
                _append_label_lines(subject_lines, current_subject, label_map)  # type: ignore[arg-type]
                # Replace last semicolon with period on the last predicate
                subject_lines[-1] = subject_lines[-1].rstrip(";") + " ."
                lines.extend(subject_lines)
                lines.append("")  # Blank line between subjects

            current_subject = t["subject_uuid"]
            subject_lines = [f"{subj_uri}"]

        subject_lines.append(f"    {pred_uri} {obj} ;")

    # Flush last subject
    if subject_lines:
        _append_label_lines(subject_lines, current_subject, label_map)  # type: ignore[arg-type]
        subject_lines[-1] = subject_lines[-1].rstrip(";") + " ."
        lines.extend(subject_lines)

    # Nodes without triples: emit as proper nodes with rdfs:label
    all_nodes = db.execute(
        "SELECT node_id, etikedoj FROM nodes ORDER BY node_id"
    )
    omitted = [
        n for n in all_nodes if n["node_id"] not in subjects_with_triples
    ]
    if omitted:
        if lines and lines[-1] != "":
            lines.append("")
        for n in omitted:
            node_id = n["node_id"]
            pairs = label_map.get(node_id)
            if not pairs:
                # No labels either - nothing useful to emit
                continue
            subj_uri = _format_turtle_uri(node_id, prefix_uris, base_uri)
            label_lines: list[str] = [f"{subj_uri}"]
            _append_label_lines(label_lines, node_id, label_map)
            label_lines[-1] = label_lines[-1].rstrip(";") + " ."
            lines.extend(label_lines)
            lines.append("")

    # Remove trailing blank line(s)
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines) + "\n"
