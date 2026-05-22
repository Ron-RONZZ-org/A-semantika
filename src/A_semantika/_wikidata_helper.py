"""Stateless helper wrapping A.core.wikidata with A-semantika data model mapping.

Provides validation, normalization, search, and metadata fetch utilities
for Wikidata property integration. All functions are stateless -- no DB
writes happen here.
"""
from __future__ import annotations

import json
import re
from typing import Any

from A import warning
from A.core.wikidata import get_property_details, search_properties

_WIKIDATA_PATTERN = re.compile(r"^(?:wdt:)?(P\d+)$", re.IGNORECASE)

# Timeout defaults appropriate for CLI UX
_SEARCH_TIMEOUT: float = 5.0
_DETAILS_TIMEOUT: float = 10.0


def is_wikidata_id(predicate_id: str) -> bool:
    """Check if a predicate ID looks like a Wikidata property.

    Matches patterns: ``P31``, ``wdt:P31``, ``WDT:P1082``.
    Does NOT match: ``rdf:type``, ``my:prop``, ``foaf:knows``.
    """
    return bool(_WIKIDATA_PATTERN.match(predicate_id.strip()))


def normalize_predicate_id(predicate_id: str) -> str:
    """Normalize a bare Wikidata P-number to ``wdt:`` prefix form.

    - ``P31`` → ``wdt:P31``
    - ``wdt:P31`` → ``wdt:P31`` (unchanged)
    - ``rdf:type`` → ``rdf:type`` (unchanged, not a Wikidata ID)

    Returns:
        Normalized predicate ID. Non-Wikidata IDs pass through unchanged.
    """
    m = _WIKIDATA_PATTERN.match(predicate_id.strip())
    if not m:
        return predicate_id.strip()
    return f"wdt:{m.group(1).upper()}"


def search_wikidata(
    query: str,
    languages: tuple[str, ...] = ("eo", "en"),
    timeout: float = _SEARCH_TIMEOUT,
) -> list[dict[str, Any]]:
    """Search Wikidata properties matching *query*.

    Results are mapped to A-semantika's predicate model:
    ``{predicate_id, label, priskribo, aliases, source}``

    Since Wikidata returns a single best-match label (not per-language),
    the returned ``label`` is a unified string suitable for display.

    Args:
        query: Free-text search string.
        languages: Language priority for label enrichment.
        timeout: Request timeout in seconds. Defaults to 5s for fast CLI.

    Returns:
        List of mapped property dicts. Empty list on network failure.
    """
    try:
        results = search_properties(
            query,
            languages=list(languages),
            timeout=timeout,
        )
    except RuntimeError:
        warning("Wikidata API neatingebla (preterlaste)")
        return []

    mapped: list[dict[str, Any]] = []
    for r in results:
        aliases: list[str] = r.get("aliasoj") or []
        mapped.append({
            "predicate_id": r.get("ligilo", ""),
            "label": r.get("etikedo", ""),
            "priskribo": r.get("priskribo", ""),
            "aliases": json.dumps(aliases, ensure_ascii=False),
            "source": "wikidata",
        })
    return mapped


def fetch_wikidata_details(
    prop_id: str,
    languages: tuple[str, ...] = ("eo", "en"),
    timeout: float = _DETAILS_TIMEOUT,
) -> dict[str, Any] | None:
    """Fetch per-language labels and details for a Wikidata property.

    Uses ``get_property_details()`` which returns separate labels for
    each requested language, suitable for populating both ``label_eo``
    and ``label_en`` columns.

    Args:
        prop_id: Wikidata property ID with or without ``wdt:`` prefix
            (e.g. ``P1082`` or ``wdt:P1082``).
        languages: Language codes to fetch labels for.
        timeout: Request timeout in seconds. Defaults to 10s.

    Returns:
        Dict mapped to A-semantika predicate model:
        ``{predicate_id, label_eo, label_en, priskribo, aliases, source}``
        or ``None`` on network failure or missing property.
    """
    bare_id = prop_id.removeprefix("wdt:").removeprefix("WDT:").strip()
    try:
        details = get_property_details(
            bare_id,
            languages=list(languages),
            timeout=timeout,
        )
    except RuntimeError:
        return None

    labels: dict[str, str] = details.get("labels") or {}
    descs: dict[str, str] = details.get("descriptions") or {}
    raw_aliases: dict[str, list[str]] = details.get("aliases") or {}

    priskribo = ""
    for lang in languages:
        if lang in descs and descs[lang]:
            priskribo = descs[lang]
            break

    merged_aliases: list[str] = []
    seen: set[str] = set()
    for lang in languages:
        for alias in raw_aliases.get(lang, []):
            if alias.lower() not in seen:
                seen.add(alias.lower())
                merged_aliases.append(alias)

    return {
        "predicate_id": f"wdt:{bare_id}",
        "label_eo": labels.get("eo", ""),
        "label_en": labels.get("en", ""),
        "priskribo": priskribo,
        "aliases": json.dumps(merged_aliases, ensure_ascii=False),
        "source": "wikidata",
    }
