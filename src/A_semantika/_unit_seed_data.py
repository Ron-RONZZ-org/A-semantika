"""Seed data for unit ontology type hierarchy and default SI units.

All data is defined as module-level dict constants and consumed by
``_unit_service.py`` for lazy seeding on first access.
"""
from __future__ import annotations

from typing import ClassVar

# ── Unit type hierarchy ─────────────────────────────────────────────────
# These are nodes in the graph, created with ``rdf:type :UnitType`` triples.
# The type node itself is a meta-type.

UNIT_TYPE_NODES: list[dict] = [
    {
        "node_id": ":UnitType",
        "etikedoj": {"eo": "Unuotipo", "en": "Unit type", "fr": "Type d'unité"},
        "parent_type": None,
    },
    {
        "node_id": ":SingularUnit",
        "etikedoj": {"eo": "Baza unuo", "en": "Singular unit", "fr": "Unité simple"},
        "parent_type": ":UnitType",
    },
    {
        "node_id": ":PrefixedUnit",
        "etikedoj": {"eo": "Prefiksita unuo", "en": "Prefixed unit", "fr": "Unité préfixée"},
        "parent_type": ":UnitType",
        "also_type": ":SingularUnit",
    },
    {
        "node_id": ":CompoundUnit",
        "etikedoj": {"eo": "Kombinita unuo", "en": "Compound unit", "fr": "Unité composée"},
        "parent_type": ":UnitType",
    },
    {
        "node_id": ":UnitProduct",
        "etikedoj": {"eo": "Unuoprodukto", "en": "Unit product", "fr": "Produit d'unité"},
        "parent_type": ":CompoundUnit",
    },
    {
        "node_id": ":UnitPower",
        "etikedoj": {"eo": "Unuopotenco", "en": "Unit power", "fr": "Puissance d'unité"},
        "parent_type": ":CompoundUnit",
    },
]

# ── SI base units ────────────────────────────────────────────────────────

SI_BASE_UNITS: list[dict] = [
    {
        "node_id": "unit:METER",
        "etikedoj": {"eo": "metro", "en": "meter", "fr": "mètre"},
        "symbol": "m",
        "ucum": "m",
    },
    {
        "node_id": "unit:KILOGRAM",
        "etikedoj": {"eo": "kilogramo", "en": "kilogram", "fr": "kilogramme"},
        "symbol": "kg",
        "ucum": "kg",
    },
    {
        "node_id": "unit:SECOND",
        "etikedoj": {"eo": "sekundo", "en": "second", "fr": "seconde"},
        "symbol": "s",
        "ucum": "s",
    },
    {
        "node_id": "unit:AMPERE",
        "etikedoj": {"eo": "ampero", "en": "ampere", "fr": "ampère"},
        "symbol": "A",
        "ucum": "A",
    },
    {
        "node_id": "unit:KELVIN",
        "etikedoj": {"eo": "kelvino", "en": "kelvin", "fr": "kelvin"},
        "symbol": "K",
        "ucum": "K",
    },
    {
        "node_id": "unit:MOLE",
        "etikedoj": {"eo": "molo", "en": "mole", "fr": "mole"},
        "symbol": "mol",
        "ucum": "mol",
    },
    {
        "node_id": "unit:CANDELA",
        "etikedoj": {"eo": "kandelo", "en": "candela", "fr": "candela"},
        "symbol": "cd",
        "ucum": "cd",
    },
]

# ── Named derived SI units ──────────────────────────────────────────────
# Each has a symbol, UCUM code, and optionally multiplier+offset for SI conversion.

DERIVED_UNITS: list[dict] = [
    {
        "node_id": "unit:RADIAN",
        "etikedoj": {"eo": "radiano", "en": "radian", "fr": "radian"},
        "symbol": "rad",
        "ucum": "rad",
    },
    {
        "node_id": "unit:STERADIAN",
        "etikedoj": {"eo": "steradiano", "en": "steradian", "fr": "stéradian"},
        "symbol": "sr",
        "ucum": "sr",
    },
    {
        "node_id": "unit:HERTZ",
        "etikedoj": {"eo": "herco", "en": "hertz", "fr": "hertz"},
        "symbol": "Hz",
        "ucum": "Hz",
    },
    {
        "node_id": "unit:NEWTON",
        "etikedoj": {"eo": "neŭtono", "en": "newton", "fr": "newton"},
        "symbol": "N",
        "ucum": "N",
    },
    {
        "node_id": "unit:PASCAL",
        "etikedoj": {"eo": "paskalo", "en": "pascal", "fr": "pascal"},
        "symbol": "Pa",
        "ucum": "Pa",
    },
    {
        "node_id": "unit:JOULE",
        "etikedoj": {"eo": "ĵulo", "en": "joule", "fr": "joule"},
        "symbol": "J",
        "ucum": "J",
    },
    {
        "node_id": "unit:WATT",
        "etikedoj": {"eo": "vato", "en": "watt", "fr": "watt"},
        "symbol": "W",
        "ucum": "W",
    },
    {
        "node_id": "unit:COULOMB",
        "etikedoj": {"eo": "kulombo", "en": "coulomb", "fr": "coulomb"},
        "symbol": "C",
        "ucum": "C",
    },
    {
        "node_id": "unit:VOLT",
        "etikedoj": {"eo": "volto", "en": "volt", "fr": "volt"},
        "symbol": "V",
        "ucum": "V",
    },
    {
        "node_id": "unit:FARAD",
        "etikedoj": {"eo": "farado", "en": "farad", "fr": "farad"},
        "symbol": "F",
        "ucum": "F",
    },
    {
        "node_id": "unit:OHM",
        "etikedoj": {"eo": "omo", "en": "ohm", "fr": "ohm"},
        "symbol": "Ω",
        "ucum": "Ohm",
    },
    {
        "node_id": "unit:SIEMENS",
        "etikedoj": {"eo": "simenso", "en": "siemens", "fr": "siemens"},
        "symbol": "S",
        "ucum": "S",
    },
    {
        "node_id": "unit:WEBER",
        "etikedoj": {"eo": "vebero", "en": "weber", "fr": "weber"},
        "symbol": "Wb",
        "ucum": "Wb",
    },
    {
        "node_id": "unit:TESLA",
        "etikedoj": {"eo": "teslo", "en": "tesla", "fr": "tesla"},
        "symbol": "T",
        "ucum": "T",
    },
    {
        "node_id": "unit:HENRY",
        "etikedoj": {"eo": "henro", "en": "henry", "fr": "henry"},
        "symbol": "H",
        "ucum": "H",
    },
    {
        "node_id": "unit:LUMEN",
        "etikedoj": {"eo": "lumeno", "en": "lumen", "fr": "lumen"},
        "symbol": "lm",
        "ucum": "lm",
    },
    {
        "node_id": "unit:LUX",
        "etikedoj": {"eo": "lukso", "en": "lux", "fr": "lux"},
        "symbol": "lx",
        "ucum": "lx",
    },
    {
        "node_id": "unit:BECQUEREL",
        "etikedoj": {"eo": "bekero", "en": "becquerel", "fr": "becquerel"},
        "symbol": "Bq",
        "ucum": "Bq",
    },
    {
        "node_id": "unit:GRAY",
        "etikedoj": {"eo": "grajo", "en": "gray", "fr": "gray"},
        "symbol": "Gy",
        "ucum": "Gy",
    },
    {
        "node_id": "unit:SIEVERT",
        "etikedoj": {"eo": "siverto", "en": "sievert", "fr": "sievert"},
        "symbol": "Sv",
        "ucum": "Sv",
    },
    {
        "node_id": "unit:KATAL",
        "etikedoj": {"eo": "katalo", "en": "katal", "fr": "katal"},
        "symbol": "kat",
        "ucum": "kat",
    },
    {
        "node_id": "unit:DEGREE_CELSIUS",
        "etikedoj": {"eo": "gradoj celsiaj", "en": "degree Celsius", "fr": "degré Celsius"},
        "symbol": "°C",
        "ucum": "Cel",
        "multiplier": 1.0,
        "offset": -273.15,
    },
]

# ── SI Prefixes ─────────────────────────────────────────────────────────

SI_PREFIXES: list[dict] = [
    {"node_id": "unit:YOTTA", "etikedoj": {"eo": "jota", "en": "yotta", "fr": "yotta"}, "symbol": "Y", "multiplier": 1e24},
    {"node_id": "unit:ZETTA", "etikedoj": {"eo": "zeta", "en": "zetta", "fr": "zetta"}, "symbol": "Z", "multiplier": 1e21},
    {"node_id": "unit:EXA", "etikedoj": {"eo": "eksa", "en": "exa", "fr": "exa"}, "symbol": "E", "multiplier": 1e18},
    {"node_id": "unit:PETA", "etikedoj": {"eo": "peta", "en": "peta", "fr": "péta"}, "symbol": "P", "multiplier": 1e15},
    {"node_id": "unit:TERA", "etikedoj": {"eo": "tera", "en": "tera", "fr": "téra"}, "symbol": "T", "multiplier": 1e12},
    {"node_id": "unit:GIGA", "etikedoj": {"eo": "giga", "en": "giga", "fr": "giga"}, "symbol": "G", "multiplier": 1e9},
    {"node_id": "unit:MEGA", "etikedoj": {"eo": "mega", "en": "mega", "fr": "méga"}, "symbol": "M", "multiplier": 1e6},
    {"node_id": "unit:KILO", "etikedoj": {"eo": "kilo", "en": "kilo", "fr": "kilo"}, "symbol": "k", "multiplier": 1e3},
    {"node_id": "unit:HECTO", "etikedoj": {"eo": "hekto", "en": "hecto", "fr": "hecto"}, "symbol": "h", "multiplier": 1e2},
    {"node_id": "unit:DEKA", "etikedoj": {"eo": "deka", "en": "deka", "fr": "déca"}, "symbol": "da", "multiplier": 1e1},
    {"node_id": "unit:DECI", "etikedoj": {"eo": "deci", "en": "deci", "fr": "déci"}, "symbol": "d", "multiplier": 1e-1},
    {"node_id": "unit:CENTI", "etikedoj": {"eo": "centi", "en": "centi", "fr": "centi"}, "symbol": "c", "multiplier": 1e-2},
    {"node_id": "unit:MILLI", "etikedoj": {"eo": "mili", "en": "milli", "fr": "milli"}, "symbol": "m", "multiplier": 1e-3},
    {"node_id": "unit:MICRO", "etikedoj": {"eo": "mikro", "en": "micro", "fr": "micro"}, "symbol": "µ", "multiplier": 1e-6},
    {"node_id": "unit:NANO", "etikedoj": {"eo": "nano", "en": "nano", "fr": "nano"}, "symbol": "n", "multiplier": 1e-9},
    {"node_id": "unit:PICO", "etikedoj": {"eo": "piko", "en": "pico", "fr": "pico"}, "symbol": "p", "multiplier": 1e-12},
    {"node_id": "unit:FEMTO", "etikedoj": {"eo": "femto", "en": "femto", "fr": "femto"}, "symbol": "f", "multiplier": 1e-15},
    {"node_id": "unit:ATTO", "etikedoj": {"eo": "ato", "en": "atto", "fr": "atto"}, "symbol": "a", "multiplier": 1e-18},
    {"node_id": "unit:ZEPTO", "etikedoj": {"eo": "zepto", "en": "zepto", "fr": "zepto"}, "symbol": "z", "multiplier": 1e-21},
    {"node_id": "unit:YOCTO", "etikedoj": {"eo": "jokto", "en": "yocto", "fr": "yocto"}, "symbol": "y", "multiplier": 1e-24},
]


# Convenience: all unit definitions in one list for seeding.
BASE_AND_DERIVED: list[dict] = SI_BASE_UNITS + DERIVED_UNITS
ALL_UNITS: list[dict] = BASE_AND_DERIVED + SI_PREFIXES
