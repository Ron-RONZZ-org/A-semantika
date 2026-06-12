"""Recenzi (interactive review) data layer — SQLite tables.
"""
from __future__ import annotations

RECENZI_SCHEMA_SQL = """
-- Review sessions
CREATE TABLE IF NOT EXISTS recenzo_sesio (
    uuid         TEXT PRIMARY KEY,
    modo         TEXT NOT NULL,          -- 'rigardi' or 'multobla'
    dato_de      TEXT,                   -- ISO start date filter
    dato_gis     TEXT,                   -- ISO end date filter
    totalo       INTEGER NOT NULL DEFAULT 0,
    korekta      INTEGER NOT NULL DEFAULT 0,
    finita       INTEGER NOT NULL DEFAULT 0,  -- 0 = ongoing, 1 = finished
    kreita_je    TEXT NOT NULL
);

-- Per-question results
CREATE TABLE IF NOT EXISTS recenzo_rezulto (
    uuid           TEXT PRIMARY KEY,
    sesio_uuid     TEXT NOT NULL REFERENCES recenzo_sesio(uuid),
    subject_uuid   TEXT NOT NULL,
    predicate_id   TEXT NOT NULL,
    object_value   TEXT NOT NULL,
    object_type    TEXT NOT NULL DEFAULT 'uri',
    korekta        INTEGER NOT NULL DEFAULT 0,  -- 0 = wrong, 1 = correct
    respondo       TEXT,                        -- what the user answered
    pozicio        INTEGER NOT NULL DEFAULT 0,
    kreita_je      TEXT NOT NULL
);
"""
