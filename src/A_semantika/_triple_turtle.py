"""Turtle (.ttl) export for Triples.

Extracted from _triple_service.py to keep that file under 500 lines.
"""
from __future__ import annotations

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
    For values with a colon where the prefix is known, the prefixed form is used.
    For all other values, the local part must be a valid Turtle PN_LOCAL
    (not start with a digit); otherwise a full ``<...>`` URI is emitted.

    Args:
        val: The URI reference string.
        prefix_uris: Mapping of prefix → namespace URI (e.g. {"rdf": "http://..."}).
        base_uri: The base URI for the default namespace (used for full URIs
                  when the value cannot be expressed as a prefixed name).

    Returns:
        A Turtle-compatible URI string (prefixed name or full URI in <...>).
    """
    if ":" in val:
        prefix, _, local = val.partition(":")
        if prefix in prefix_uris and _PN_LOCAL_RE.match(local):
            return val  # Already a valid prefixed name
    # Check if val can be a default-prefix name
    if _PN_LOCAL_RE.match(val):
        return f":{val}"
    # Fall back to full URI
    return f"<{base_uri}{val}>"


def export_turtle(
    db: Any,
    prefix_uris: dict[str, str],
    base_uri: str = "https://example.org/",
) -> str:
    """Export all triples to Turtle (.ttl) format.

    Triples are grouped by subject, with predicates formatted as:
      subject
          predicate1 object1 ;
          predicate2 object2 ;
          predicate3 object3 .

    Nodes that have no outgoing triples are listed as Turtle comments
    at the end of the output so they are not silently lost.

    Args:
        db: Database instance (SQLiteDB or compatible).
        prefix_uris: Mapping of prefix → namespace URI.
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

    triples = db.execute(
        """SELECT t.*, n.etikedoj AS subj_label, p.etikedoj AS pred_etikedoj
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
            # Typed literal — handle custom datatypes, not only xsd:
            escaped_val = _escape_turtle_literal(t["object_value"])
            dtype = t["object_datatype"]
            if ":" in dtype:
                ns, _, local = dtype.partition(":")
                if ns == "xsd":
                    obj = f'"{escaped_val}"^^xsd:{local}'
                else:
                    # Custom datatype — emit full URI or prefixed form
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
                # Replace last semicolon with period on the last predicate
                subject_lines[-1] = subject_lines[-1].rstrip(";") + " ."
                lines.extend(subject_lines)
                lines.append("")  # Blank line between subjects

            current_subject = t["subject_uuid"]
            subject_lines = [f"{subj_uri}"]

        subject_lines.append(f"    {pred_uri} {obj} ;")

    # Flush last subject
    if subject_lines:
        subject_lines[-1] = subject_lines[-1].rstrip(";") + " ."
        lines.extend(subject_lines)

    # Append nodes without triples as comments
    all_nodes = db.execute(
        "SELECT node_id, etikedoj FROM nodes ORDER BY node_id"
    )
    omitted = [
        n for n in all_nodes if n["node_id"] not in subjects_with_triples
    ]
    if omitted:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(
            "# Nodes without outgoing triples (listed below for reference):"
        )
        for n in omitted:
            label = str(n.get("etikedoj", "{}"))
            lines.append(
                f"#   :{n['node_id']}  {label}"
            )

    return "\n".join(lines)
