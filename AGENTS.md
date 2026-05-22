# AGENTS.md — Rules for A-semantika
This file extends [A-workspace](../AGENTS.md).

This file extends root A-core AGENTS.md for the A-semantika plugin.

## Project Overview

A-semantika is a pure semantic-arc-based world modelling system (RDF-style triple store) for fragmented, machine-inferencable knowledge note-taking.

**Key difference from A-encik:**
- **A-encik**: text-file (.enc) based entries, semantic links as auxiliary feature
- **A-semantika**: triple-first — one statement at a time, no need to create full files

A-encik's existing `encik semantika` subsystem remains unchanged. Deprecation deferred until A-semantika is stable.

## Relationship to A-core

**A-semantika depends on A-core** for:
- `A` package (i18n, output, subprocess)
- `A.core.service.CRUDService` — base class for NodeService, PredicateService, PredicateGroupService
- `A.data.base.SQLiteDB` — database layer
- `A.data.search.FTSConfig` — FTS5 full-text search config
- `A.core.paths` — data_dir, config_dir
- `A.utils.interactive.confirm_action` — confirmation prompts
- Plugin discovery via entry points

All source code must import from `A`, never duplicate utilities.

## Architecture

```
src/A_semantika/
├── __init__.py        # exports: app
├── cli.py             # Typer app with 4 subcommand groups
├── service.py         # NodeService, PredicateService, PredicateGroupService, TripleService
└── data/
    └── storage.py     # Schema DDL, get_db(), init_db(), get_service() singletons
tests/
├── conftest.py        # autouse isolation fixture
├── test_nodes.py
├── test_predicates.py
├── test_predicate_groups.py
├── test_triples.py
└── test_cli.py
```

## Final DB Schema

```sql
-- Nodes: entities in the knowledge graph
CREATE TABLE nodes (
    uuid        TEXT PRIMARY KEY,
    etikedoj    TEXT NOT NULL DEFAULT '{}',  -- JSON: {"eo": "Vorto", "en": "Word"}
    label_text  TEXT NOT NULL DEFAULT '',     -- denormalized from etikedoj (for FTS5)
    difinoj     TEXT NOT NULL DEFAULT '{}',  -- JSON definitions
    difin_text  TEXT NOT NULL DEFAULT '',     -- denormalized from difinoj (for FTS5)
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);

-- Predicates: semantic properties (rdf:type, wdt:P1082, custom, etc.)
CREATE TABLE predicates (
    uuid          TEXT PRIMARY KEY,
    predicate_id  TEXT NOT NULL UNIQUE,
    source        TEXT NOT NULL DEFAULT 'manual',  -- 'wikidata'|'manual'|'owl'|'rdfs'
    label_en      TEXT DEFAULT '',
    label_eo      TEXT DEFAULT '',
    priskribo     TEXT DEFAULT '',
    aliases       TEXT NOT NULL DEFAULT '[]',
    kreita_je     TEXT NOT NULL,
    modifita_je   TEXT NOT NULL
);

-- Predicate groups (logical collections of predicates)
CREATE TABLE predicate_groups (
    uuid         TEXT PRIMARY KEY,
    group_name   TEXT NOT NULL UNIQUE,
    kreita_je    TEXT NOT NULL,
    modifita_je  TEXT NOT NULL
);

CREATE TABLE predicate_group_members (
    uuid            TEXT PRIMARY KEY,
    group_uuid      TEXT NOT NULL REFERENCES predicate_groups(uuid),
    predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
    kreita_je       TEXT NOT NULL
);

-- Triples: the core semantic arcs (subject-predicate-object)
-- Compound SPOK PK mirrors RDF triple store indexing.
CREATE TABLE triples (
    subject_uuid    TEXT NOT NULL REFERENCES nodes(uuid),
    predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
    object_type     TEXT NOT NULL DEFAULT 'uri',   -- 'uri' or 'literal'
    object_value    TEXT NOT NULL,
    object_lang     TEXT DEFAULT NULL,
    object_datatype TEXT DEFAULT NULL,
    object_node_uuid TEXT GENERATED ALWAYS AS (
        CASE WHEN object_type='uri' THEN object_value ELSE NULL END
    ) STORED REFERENCES nodes(uuid),
    kreita_je       TEXT NOT NULL,
    PRIMARY KEY (subject_uuid, predicate_id, object_value, object_type)
) WITHOUT ROWID;

-- Indexes
CREATE INDEX idx_triples_pos ON triples(predicate_id, object_value, subject_uuid);
CREATE INDEX idx_triples_osp ON triples(object_value, object_type, predicate_id, subject_uuid);
CREATE INDEX idx_triples_pred_subj ON triples(predicate_id, subject_uuid);
CREATE INDEX idx_pred_group_members_group ON predicate_group_members(group_uuid);
CREATE INDEX idx_pred_group_members_pred  ON predicate_group_members(predicate_id);

-- FTS5 on nodes
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    uuid UNINDEXED,
    label_text,
    difin_text,
    content=nodes,
    content_rowid=rowid,
    tokenize='unicode61'
);

-- Fallback non-FTS label search index
CREATE INDEX idx_nodes_label_text ON nodes(label_text);
```

## Service Layer

### NodeService (extends CRUDService)
- FTS5 on `label_text` + `difin_text` (via `FTSConfig`)
- Override `_post_create` / `_post_update` to auto-populate `label_text` from `etikedoj` JSON
- UUID override on `aldoni`: optional `[UUID]` positional arg for manual UUID assignment

### PredicateService (extends CRUDService)
- Search on `predicate_id`, `label_en`, `label_eo`, `priskribo`
- No undo/trash needed (predicates are lightweight metadata)

### PredicateGroupService (extends CRUDService)
- Member management: `add_member()`, `remove_member()`, `list_members()`

### TripleService (custom, NOT CRUDService)
```python
def add(subject_uuid, predicate_id, object_value, object_type="uri",
        object_lang=None, object_datatype=None) -> dict
def remove(subject_uuid=None, predicate_id=None, object_value=None,
           object_type=None) -> int
def get_by_subject(uuid) -> list[dict]
def get_by_predicate(predicate_id, limit=100) -> list[dict]
def get_by_object(object_value, object_type=None) -> list[dict]
def get_by_sp(subject_uuid, predicate_id) -> list[dict]
def exists(subject_uuid, predicate_id, object_value, object_type="uri") -> bool
def count() -> int
def get_stats() -> dict
def export_turtle(base_uri="https://example.org/") -> str
```

## CLI Commands

```
A semantika aldoni <subject> <predicate> <object>
  [-U / --uri]        object is a URI node reference
  [--int]             integer literal
  [-f / --float]      float literal
  [-b / --bool]       boolean literal
  [-l / --lingvo]     language tag for string literals
  [-u / --unuo]       unit UUID for numeric values
  [-y / --yes]        skip confirmation

A semantika nodo aldoni [UUID]
  [-e / --etikedo "LANG::STR"]*
  [-d / --difino "LANG::STR"]*
  [-t / --tipo UUID]*               [shortcut: rdf:type]
  [-so / --superklaso UUID]*        [shortcut: rdfs:subClassOf]
  [--ne UUID]*                      [shortcut: owl:disjointWith]
  [-iv / --invers UUID]*            [shortcut: owl:inverseOf]
  [-y / --yes]

A semantika predikato aldoni <predicate-id>
  [-e / --etikedo "LANGCODE::STR"]*
  [-a / --aliaso STR]*
  [-y / --yes]

A semantika predikat-grupo aldoni <group-name>
A semantika predikat-grupo importi <file>

# Standard CRUD commands (all subcommand groups):
  ls vidi modifi forigi serci
```

## Confirmation Preview

```
┌───────────┬────────────┬───────────┐
│ Subject   │ Predicate  │ Object    │
├───────────┼────────────┼───────────┤
│ Hundo     │ estas tipo │ Mamulo    │  ← labels FIRST
│ (eo)      │ de         │ (eo)      │
│ abc-12345 │ rdf:type   │ def-67890 │  ← raw IDs SECOND
└───────────┴────────────┴───────────┘
→ URI
```

- `box=BOX_SIMPLE` (from `rich.box`)
- Labels row first, raw IDs second
- Footnote shows object type + metadata
- `confirm_action()` for prompt (locale-aware)
- `-y` to skip

## Phasing

| Phase | Scope | Deps |
|-------|-------|------|
| **P1** | Core triple store (schema, services, CLI, Turtle export, tests) | A-core (stdlib) |
| **P2** | Wikidata integration (`predikato serci` + `predikato aldoni`) | `A.core.wikidata` extraction |
| **P3** | OWL/RDFS import (RDFS hierarchy + basic OWL) | None |

## Code Standards

1. Use `tr_multi()` for all user-facing strings (eo, en, fr)
2. Use `error()` for errors, `info()` for info
3. Type hints on all public functions
4. Docstrings on all public functions
5. Tests required for all modules
6. WAL mode for SQLite
7. FTS5 for full-text search
8. Import from `A` — never duplicate utilities
9. `box=BOX_SIMPLE` on all Rich tables
10. UUID primary keys on all tables (except triples — compound PK)

## Testing

```bash
cd A-semantika
uv run pytest tests/ -v
```

All tests must have `autouse=True` fixture in `conftest.py` that:
- monkeypatches `data_dir` to `tmp_path`
- resets the `get_db()` singleton
- uses `typer.testing.CliRunner` for CLI tests

## Branch Convention

Use `main` as the primary branch. All development on `main`.

## Package Manager

Use `uv` for development. See A-core AGENTS.md for details.

## Reference

- Issue: https://github.com/Ron-RONZZ-org/A-workspace/issues/8
- Final CLI spec: https://github.com/Ron-RONZZ-org/A-workspace/issues/8#issuecomment-4521473446
- Schema evaluation: https://github.com/Ron-RONZZ-org/A-workspace/issues/8#issuecomment-4520977949
