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
- `A.utils.interactive.select_candidate` — numbered-table item picker (Issue #8 R3)
- Plugin discovery via entry points

All source code must import from `A`, never duplicate utilities.

## Architecture

```
src/A_semantika/
├── __init__.py            # exports: app
├── cli.py                 # Typer app with 4 subcommand groups
├── service.py             # NodeService, PredicateService, PredicateGroupService, TripleService
├── _wikidata_helper.py    # Wikidata API adapter (validation, search, metadata fetch)
├── _cli_helpers.py        # Shared CLI helpers (pick_triple, type flag validation)
├── _cli_modify.py         # Root `modifi` command (Issue #8 R3 + Issue #10 EO)
├── _cli_nodo.py           # Nodo subcommand CLI
├── _cli_predikato.py      # Predikato subcommand CLI (+ Wikidata flags)
├── _cli_predikat_grupo.py # Predikat-grupo subcommand CLI
├── _cli_query.py          # Root query commands: serci, vidi, eksporti (Issue #10 EO)
├── _cli_rubujo.py         # Rubujo (trash) subcommand group: ls, restaurigi, malplenigi, forigi
├── _cli_triples.py        # Root triple CLI: aldoni, forigi
├── _node_service.py       # NodeService (CRUDService + FTS5)
├── _predicate_service.py  # PredicateService (CRUDService + LIKE search)
├── _predicate_group_service.py  # PredicateGroupService (CRUDService + member mgmt)
├── _triple_search.py      # Triple search by partial labels (Issue #8 R2)
├── _triple_service.py     # TripleService (custom, non-CRUDService)
├── _triple_turtle.py      # Turtle (.ttl) export (extracted from _triple_service.py for < 500 lines)
├── _preview.py            # Rich table preview helpers
└── data/
    ├── storage.py         # Schema DDL, get_db(), init_db(), get_service() singletons
    └── migrations.py      # DB migrations: uuid→node_id, predicates JSON, UNIQUE constraints
tests/
├── conftest.py                      # autouse isolation fixture
├── test_cli_deprecated.py           # Deprecated alias tests
├── test_cli_export.py               # eksporti Turtle export tests
├── test_cli_help.py                 # Help & command discovery
├── test_cli_nodo.py                 # Nodo CLI CRUD
├── test_cli_predikat_grupo.py       # Predikat-grupo CLI CRUD
├── test_cli_predikato.py            # Predikato CLI CRUD
├── test_cli_rubujo.py               # rubujo (trash) CLI tests
├── test_cli_triples.py              # Triple CLI CRUD
├── test_cli_type_flags.py           # B3: type flag validation
├── test_cli_wikidata.py             # Wikidata integration tests
├── test_edge_inputs.py              # Edge: special chars, empty inputs
├── test_fts5_sanitization.py        # Edge: FTS5 special chars
├── test_multi_forigi.py             # Edge: multi-identifier forigi
├── test_node_arcs.py                # Edge: nodo aldoni with arcs
├── test_nodes.py                    # NodeService unit tests
├── test_nodo_errors.py              # Edge: nodo error handling
├── test_nodo_vidi_ensure.py         # Edge: vidi + ensure_predicate
├── test_predicate_groups.py         # PredicateGroupService tests
├── test_predicates.py               # PredicateService tests
├── test_preview_helpers.py          # Edge: preview table + confirm
├── test_search_helpers.py           # Edge: UUID heuristic, type flags
├── test_storage_default_predicates.py  # DB: default predicate seeding
├── test_storage_migrations.py       # DB: schema migrations
├── test_storage_schema.py           # DB: schema & WAL mode
├── test_triple_modifi_edge.py       # Edge: modifi + confirm triples
├── test_triple_search.py            # Triple search unit tests
├── test_triples.py                  # TripleService unit tests
├── test_turtle_export_edge.py       # Edge: custom datatype export
└── test_wikidata_helper.py          # Wikidata helper unit tests
```

## Final DB Schema

#### Turtle Export (`eksporti`)

The `eksporti` command exports the entire triple store to standard Turtle (.ttl) format.
Node labels (from `etikedoj` JSON) are emitted as standard W3C `rdfs:label` triples with
language tags — this follows the RDFS recommendation for resource annotation.

**Output structure:**
```turtle
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:HUNDO
    rdf:type :KATO ;
    rdfs:label "Hundo"@eo,
               "Dog"@en .
```

Nodes without outgoing triples but with labels appear as standalone `rdfs:label` nodes.
Nodes with neither triples nor labels are silently omitted.

```sql
-- Nodes: entities in the knowledge graph
CREATE TABLE nodes (
    node_id     TEXT PRIMARY KEY,  -- human-readable ID (e.g. SPACO), or auto-generated UUID
    etikedoj    TEXT NOT NULL DEFAULT '{}',  -- JSON: {"eo": "Vorto", "en": "Word"}
    label_text  TEXT NOT NULL DEFAULT '',     -- denormalized from etikedoj (for FTS5)
    difinoj     TEXT NOT NULL DEFAULT '{}',  -- JSON definitions
    difin_text  TEXT NOT NULL DEFAULT '',     -- denormalized from difinoj (for FTS5)
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);

-- Predicates: semantic properties (rdf:type, wdt:P1082, custom, etc.)
CREATE TABLE predicates (
    predicate_id  TEXT PRIMARY KEY,  -- content-based ID (e.g. rdf:type, wdt:P31)
    source        TEXT NOT NULL DEFAULT 'manual',  -- 'wikidata' | 'manual' | 'owl' | 'rdfs' | 'rdf'
    etikedoj      TEXT NOT NULL DEFAULT '{}',  -- JSON: {"eo": "...", "en": "...", ...}
    priskriboj    TEXT NOT NULL DEFAULT '{}',  -- JSON: {"eo": "...", "en": "...", ...}
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
    kreita_je       TEXT NOT NULL,
    UNIQUE(group_uuid, predicate_id)
);

-- Triples: the core semantic arcs (subject-predicate-object)
-- Compound SPOK PK mirrors RDF triple store indexing.
CREATE TABLE triples (
    subject_uuid    TEXT NOT NULL REFERENCES nodes(node_id),
    predicate_id    TEXT NOT NULL REFERENCES predicates(predicate_id),
    object_type     TEXT NOT NULL DEFAULT 'uri',   -- 'uri' or 'literal'
    object_value    TEXT NOT NULL,
    object_lang     TEXT DEFAULT NULL,
    object_datatype TEXT DEFAULT NULL,
    object_node_uuid TEXT GENERATED ALWAYS AS (
        CASE WHEN object_type='uri' THEN object_value ELSE NULL END
    ) STORED REFERENCES nodes(node_id),
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
    node_id UNINDEXED,
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
- Stores multilingual labels/descriptions as JSON dicts: `etikedoj` / `priskriboj`
- Search on `predicate_id`, `etikedoj`, `priskriboj`, `aliases` via LIKE
- No undo/trash needed (predicates are lightweight metadata)
- Custom `create()` / `update()` with JSON serialization of dict fields

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
    def export_turtle(base_uri="https://example.org/") -> str  # rdfs:label emitted for node labels
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
  [-y / --jes]        skip confirmation (was --yes, kept as alias)

A semantika forigi <subject> [<predicate> [<object>]]
  [-y / --jes]
  If predicate/object omitted → interactive picker via partial label search

A semantika modifi <subject> [<predicate> [<object>]]
  [--nova-subjekto / -ns]  [--nova-predikato / -np]  [--nova-objekto / -no]
  Deprecated: --new-subject / --new-predicate / --new-object (hidden aliases)
  [-y / --jes]
  If predicate/object omitted → interactive picker via partial label search

A semantika serci [--subjekto LABEL] [--predikato LABEL] [--objekto LABEL]
  Deprecated: --subject / --predicate / --object (hidden aliases)
  Labels are resolved via partial matching (UUID prefix, FTS5 label, or raw text)
  Backward compat: serci <single-label> searches across all three fields

A semantika nodo aldoni [UUID]
  [-e / --etikedo "LANG::STR"]*
  [-d / --difino "LANG::STR"]*
  [-t / --tipo UUID]*               [shortcut: rdf:type]
  [-so / --superklaso UUID]*        [shortcut: rdfs:subClassOf]
  [--ne UUID]*                      [shortcut: owl:disjointWith]
  [-iv / --invers UUID]*            [shortcut: owl:inverseOf]
  [-y / --jes]

A semantika predikato aldoni <predicate-id>
  [-e / --etikedo "LANGCODE::STR"]*   # Repeatable, e.g. -e "eo::tipo" -e "en::type"
  [-p / --priskribo "LANGCODE::STR"]* # Repeatable, e.g. -p "eo::Priskribo"
  [-y / --jes]

A semantika predikato modifi <predicate-id>
  [-e / --etikedo "LANGCODE::STR"]*   # Merge by default: add/update languages
  [-p / --priskribo "LANGCODE::STR"]* # Merge by default: add/update descriptions
  [-r / --anstatauxigi]               # Replace instead of merge (clears existing)
  [-y / --jes]

A semantika predikato vidi <predicate-id>   # Shows all languages from etikedoj + priskriboj
A semantika predikato ls                     # Single label column (eo/en fallback)

A semantika predikat-grupo aldoni <group-name>
A semantika predikat-grupo importi <file>

# Standard CRUD commands (all subcommand groups):
  ls vidi modifi forigi serci

# Trash commands (rubujo subcommand group):
  rubujo ls              # List trashed nodes
  rubujo restaurigi       # Restore node(s) from trash (primary name, no accent)
  rubujo restaŭrigi       # Deprecated hidden alias
  rubujo restauxrigi      # Deprecated hidden alias
  rubujo malplenigi       # Empty trash (--days N for age filter)
  rubujo forigi           # Permanently delete specific node from trash
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

| Phase | Scope | Deps | Status |
|-------|-------|------|--------|
| **P1** | Core triple store (schema, services, CLI, Turtle export, tests) | A-core (stdlib) | ✅ Complete |
| **P2** | Wikidata integration (`predikato serci` + `predikato aldoni`) | `A.core.wikidata` extraction | ✅ Complete |
| **P3** | OWL/RDFS import (RDFS hierarchy + basic OWL) | None | ⏳ Planned |
| **I8-R1** | `--jes` flag rename + help clarification (Issue #8) | None | ✅ Complete |
| **I8-R2** | Partial label search for `serci` (Issue #8) | `A_semantika._triple_search` | ✅ Complete |
| **I8-R3** | Interactive search-then-select picker for `forigi`/`modifi` (Issue #8) | `A.utils.interactive.select_candidate` | ✅ Complete |
| **I9** | Predicate JSON migration + UX cleanup (Issue #9) | JSON `etikedoj`/`priskriboj`, merge/replace `modifi` | ✅ Complete |

| **I18** | Seed default RDF/OWL predicates at DB creation (Issue #18) | `DEFAULT_PREDICATES` in `data/storage.py` | ✅ Complete |

## Critical Bugs Fixed (May 2026)

### Issue #5: Turtle Export Syntax Error
**Fixed**: Invalid Turtle syntax (incorrect semicolon/period placement) in `_triple_service.py:export_turtle()`
- Now properly groups triples by subject
- Replaces trailing `;` with ` .` only on last predicate per subject
- Exports valid Turtle parseable by standard RDF parsers

### Issue #6: Missing Predicate Validation
**Fixed**: `_cli_triples.py:aldoni()` now validates predicate exists before triple creation
- Was producing cryptic FK constraint errors
- Now returns user-friendly "Predicate not found" message
- Added explicit check: `pred_svc.get_by_predicate_id(predicate)` before `triple_svc.create()`

### Issue #7: Race Condition in Predicate Creation
**Fixed**: `_cli_nodo.py:_ensure_predicate()` now properly handles concurrent operations
- Was silently ignoring ALL errors with bare `pass`
- Now only catches UNIQUE constraint violations
- Re-raises validation/FK/other errors to surface real problems
- Thread-safe predicate creation via typed shortcuts (--tipo, --superklaso, etc.)

### Issue #8: CLI Improvements (Multi-phase)
**Phase 1 — `--jes` flag rename + help clarifications**
- Renamed `--yes` to `--jes` across all 4 CLI files (nodo, predikato, predikat-grupo, triples)
- Kept `-y`/`--yes` as backward-compatible aliases
- Clarified `--str`/`--int`/`--float`/`--bool` help texts in `_cli_triples.py`

**Phase 2 — Partial label search for `serci`**
- Created `_triple_search.py` with `resolve_subjects()`, `resolve_predicates()`, `resolve_objects()`
- Added `search_triples_by_labels()` — triples search by partial labels with FTS5 fallback
- Added `search_triples()` multi-filter method to `TripleService`
- Updated `serci()` CLI to accept `--subject`/`--predicate`/`--object` with partial label matching
- Label-only backward compat: `serci <label>` searches across subject/predicate/object labels

**Phase 3 — Interactive search-then-select picker for `forigi`/`modifi`**
- Added `_pick_triple()` helper using `select_candidate` from `A.utils.interactive`
- Made `predicate`/`object` optional in `forigi()` — missing args trigger interactive picker
- Made `predicate`/`object` optional in `modifi()` — missing args trigger interactive picker
- Added CLI integration tests for all interactive modes (subject-only, subject+predicate, no-match)
- Fixed fragile UUID parsing in tests by using explicit UUIDs instead of `nodo ls` output parsing

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
11. **Error Handling**: Never use bare `except: pass` — always catch specific exceptions and re-raise if not expected
12. **UUID Ambiguity**: Always catch `AmbiguousUUIDError` separately from generic "not found" errors; propagate to user with clear message

## Testing

```bash
cd A-semantika
uv run pytest tests/ -v
```

All tests must have `autouse=True` fixture in `conftest.py` that:
- monkeypatches `data_dir` to `tmp_path`
- resets the `get_db()` singleton
- uses `typer.testing.CliRunner` for CLI tests

## Package Manager

Use `uv` for development. See A-core AGENTS.md for details.

## Reference

### Feature/Planning Issues
- Issue: https://github.com/Ron-RONZZ-org/A-workspace/issues/8
- Final CLI spec: https://github.com/Ron-RONZZ-org/A-workspace/issues/8#issuecomment-4521473446
- Schema evaluation: https://github.com/Ron-RONZZ-org/A-workspace/issues/8#issuecomment-4520977949
- P2 Wikidata integration: https://github.com/Ron-RONZZ-org/A-semantika/issues/2

### Critical Bugs Fixed (May 2026)
- Issue #5: CRITICAL: Turtle export produces invalid syntax
- Issue #6: CRITICAL: Missing predicate validation allows invalid triples
- Issue #7: CRITICAL: Race condition in predicate creation during concurrent operations
- Issue #8: CLI improvements: `--jes` flag rename, partial label search, interactive picker
- Issue #15: Ungraceful error handling for UNIQUE constraint violations in `nodo aldoni`/`forigi`
- Issue #10: Esperanto locale compliance — all user-facing argument/option names in EO; trilingual output for predikato display; backward compat aliases for renamed flags; split _cli_triples.py into _cli_helpers.py, _cli_modify.py, _cli_query.py (<500 lines)
- Issue #12: **5 medium-severity bugs + code quality fixes**:
  - M1: FTS5 query sanitization — strip special chars that cause syntax errors
  - M2: Narrowed `except ValueError: pass` to only suppress "already exists"
  - M3: UUID heuristic tightened — rejects short non-hex labels like "tipo", "Hundo"
  - M4: None dereference guard for `new_object` in `_cli_modify.py`
  - M5: Schema already includes `object_unit` (verified, documented)
  - L1-L4: Indent fix, `import uuid` at module level, inline imports lifted, custom Turtle datatypes
  - S1-S4: LIKE COLLATE NOCASE, predicate validation before confirm, consistent DB patterns, `clear_members()` method
  - 40 new edge case tests in `test_edge_cases.py` (195 total)

### Issue #R2: Code Review Round 2 — Critical/Medium Fixes (May 2026)

**Scope:** 14 fixes from a comprehensive code review covering code quality, missing features, test gaps, and monolith splitting.

#### C1: Critical None dereference in `modifi` preview — `_cli_modify.py`
- `resolve_node_label(node_svc, new_object)` used the raw None-able parameter instead of the resolved `new_obj` value
- Triggers when `modifi` is called with `--nova-subjekto` but WITHOUT `--nova-objekto` and WITHOUT `-y`
- **Fix:** `new_object` → `new_obj`

#### C2: Missing `rubujo` subcommand group — `_cli_rubujo.py` (NEW)
- Added trash management CLI per workspace standard: `ls`, `restaŭrigi`/`restauxrigi`, `malplenigi`, `forigi`
- Registered as `rubujo_app` in `cli.py`
- `_resolve_trash_node()` helper searches `nodes_rubujo` table directly (takes `node_id`, no dead `node_svc` param)
- 5 new CLI integration tests

#### C3: `NodeService.restore()` did not re-index FTS — `_node_service.py`
- After restoring a node from trash, FTS was not re-indexed
- Subsequent `_remove_from_fts()` caused "database disk image is malformed" SQLite error
- **Fix:** Added `_index_fts(node_id)` call after restore

#### C4: `NodeService.permanent_delete()` not overridden — `_node_service.py`
- CRUDService base class uses `WHERE uuid = ?` but NodeService uses `node_id` column
- Caused `OperationalError: no such column: uuid`
- **Fix:** Added `permanent_delete()` override using `node_id` column

#### M1: Mutating input parameter — `_node_service.py:create()`
- `data.pop("node_id", None)` mutated the caller's dict
- **Fix:** Changed to `data.get("node_id")`

#### M2: `PredicateService.delete()` ignores `soft=True` silently — `_predicate_service.py`
- `soft=True` parameter accepted but always hard-deletes
- **Fix:** Added `warning()` when `soft=True` is passed

#### M3: Moved `resolve_deprecated()` — `_cli_helpers.py` + `_cli_query.py` + `_cli_modify.py`
- Cross-module import: `_cli_modify.py` imported from `_cli_query.py`
- **Fix:** Moved to `_cli_helpers.py` where it logically belongs

#### M4: Dead code in `_cli_nodo.py:vidi()` — `_cli_nodo.py`
- `for lang, val in labels.items() if isinstance(labels, dict) else []` — the `else []` branch is dead code
- `labels` is always a `dict` at that point (guaranteed by earlier error handling)
- **Fix:** Removed dead branch

#### M5: Split `data/storage.py` (< 500 lines) — `data/migrations.py` (NEW)
- storage.py was 540 lines (> 500 limit)
- Extracted 3 migration functions to `data/migrations.py`
- storage.py reduced to 253 lines; migrations.py is 312 lines

#### T1: Migration tests for `migrate_nodes_uuid_to_node_id()` — `test_storage.py`
- 4 tests: rename, preserve data, idempotent, already-migrated
- Tests old-schema creation → migration → verification

#### T2: Migration tests for `migrate_predicates_uuid_to_predicate_id()` — `test_storage.py`
- 4 tests: flat-to-JSON, JSON-preserved, idempotent, already-migrated
- Tests both legacy schema variants (flat labels + JSON labels with uuid PK)

#### T3: `eksporti -o` file output tests — `test_cli_export.py` (NEW)
- 4 tests: file output, stdout, custom base URI, valid Turtle structure

### Issue #19: Code Review Remaining Findings (May 2026)
**Scope:** 5 remaining findings from the Issue #12 code review that were not covered by the first fix round.

#### Fix 1: Bare `except: pass` in NodeService.delete() — #19-V1
**File:** `_node_service.py:delete()`
- Replaced bare `except: pass` with `warning()` log of the exception
- AGENTS.md Rule 11 mandates no bare `except: pass`

#### Fix 2: Dead code in aldoni() after Cancelled — #19-B1
**File:** `_cli_triples.py:aldoni()`
- Removed 3 unreachable lines (copy-paste artifact) after `raise typer.Exit(0)`

#### Fix 3: FTS re-index not wrapped in transaction — #19-B4
**File:** `_node_service.py:update()`
- `_remove_from_fts()` + `_index_fts()` now run inside a transaction
- Prevents partial FTS corruption if re-index fails after removal

#### Fix 4: Missing UNIQUE constraint on predicate_group_members — #19-S1
**File:** `data/storage.py:SCHEMA_SQL` + migration
- Added `UNIQUE(group_uuid, predicate_id)` to `predicate_group_members` DDL
- Created `_migrate_predicate_group_members_unique()` for existing databases
- Migration deduplicates existing rows (first-wins via INSERT OR IGNORE)
- Swaps tables with pragma foreign_keys=OFF/ON (same pattern as predicates migration)

#### Fix 5: AGENTS.md schema outdated — #19-S3
**File:** `AGENTS.md`
- Updated `predicates` schema: removed old `uuid TEXT PRIMARY KEY`, `predicate_id` is now the PK
- Added `UNIQUE(group_uuid, predicate_id)` to `predicate_group_members` in docs

### Issue #15: Human-Readable Node IDs + Graceful Error Handling (May 2026)

**Scope:** Two changes — column rename (`uuid` → `node_id` for human-readable IDs) and graceful `IntegrityError` handling.

#### Part 1: Column Rename `uuid` → `node_id`

The `nodes` table now uses `node_id TEXT PRIMARY KEY` instead of `uuid TEXT PRIMARY KEY`. Human-readable strings (e.g. `SPACO`, `HOMOTEST`) are valid IDs. Auto-generated UUIDs still work when no ID is provided.

**Key changes:**

| Area | File | What |
|------|------|------|
| Schema | `data/storage.py` | `nodes.uuid` → `nodes.node_id`; `REFERENCES nodes(uuid)` → `nodes(node_id)`; FTS5 `uuid UNINDEXED` → `node_id UNINDEXED` |
| Service | `_node_service.py` | 7 CRUDService overrides updated: `get`, `delete`, `_move_to_trash`, `restore`, `_remove_from_fts`, `_index_fts`, `_ensure_fts` — all use `node_id` column |
| FTS5 | `_node_service.py` | Custom `_ensure_fts()` creates schema with `node_id UNINDEXED`; `_index_fts()` self-contained (avoids A-core `build_index_sql` which hardcodes `uuid`) |
| FTS5 | `_node_service.py` | `search()` JOIN: `f.uuid` → `f.node_id` |
| CLI | `_cli_nodo.py`, `_cli_triples.py`, `_cli_modify.py`, `_cli_query.py`, `_preview.py` | All `node["uuid"]` → `node["node_id"]`; help text `"UUID"` → `"ID"`/`"Indekso"` |
| Tests | All 4 test files | `{"uuid": ...}` → `{"node_id": ...}`; assertions use `node["node_id"]` |

**Scope:** A-semantika only. `predicates`, `predicate_groups`, `predicate_group_members` keep their `uuid` columns. Other A-modules (A-encik, A-vorto) keep their auto-generated UUIDs.

#### Part 2: Friendly IntegrityError Handling

Raw `IntegrityError` tracebacks in `nodo aldoni` and `nodo forigi` are caught and shown as user-friendly messages.

| Before | After |
|--------|-------|
| `$ A semantika nodo aldoni <existing-id>` → raw traceback `IntegrityError: UNIQUE constraint failed: nodes.node_id` | `[✗] Node already exists. Use 'A semantika nodo modifi ...' to modify it.` |
| `$ A semantika nodo forigi <id>` (corrupted trash) → `Eraro forigante ...: UNIQUE constraint failed: nodes_rubujo.node_id` | `Nodo ... jam estas en la rubujo` (or handled by A-core C4) |

**Changes:**

| Change | File | What |
|--------|------|------|
| **C2** | `_node_service.py:create()` | Catches `IntegrityError` on INSERT → raises `ValueError` with "already exists" guidance |
| **C3** | `_cli_nodo.py:aldoni()` | Catches `ValueError` from service → shows `error()` + clean `typer.Exit(1)` |
| **C4** | `A-core/service.py:_move_to_trash()` | `INSERT` → `INSERT OR REPLACE` — prevents trash-duplicate at source (separate A-core PR) |
| **C5** | `_cli_nodo.py:forigi()` | Filters raw `"UNIQUE constraint failed"` → friendly "already in trash" message |

**C1 removed:** UUID format validation was removed — human-readable IDs are now valid and expected.

**Tests:** Updated in `test_nodes.py` and `test_edge_cases.py`:
- Human-readable custom ID via CLI
- Duplicate node_id with friendly error message
- Auto-generated ID still works
- Double delete is safe

**Upstream dependency:** A-core PR `fix/move-to-trash-insert-or-replace` (C4) — one-word change, fully backward compatible.

### Issue #13: Multi-Identifier `forigi` (May 2026)
**Scope:** `nodo forigi`, `predikato forigi`, `predikat-grupo forigi` now accept multiple positional args.

**Pattern (per A-workspace `forigi` Contract):**
1. Accept `list[str]` positional args
2. Resolve each identifier independently — per-item errors don't block others
3. Show batch preview table of all resolved items
4. Single confirmation prompt: "Delete these N items?"
5. Per-item delete with partial success reporting (`"Deleted X of Y items"`)
6. 3-phase implementation: resolve → confirm → execute

**Commands updated:**
- `nodo forigi <node_ids...>` — accepts multiple node_id prefixes
- `predikato forigi <predicate_ids...>` — accepts multiple predicate IDs
- `predikat-grupo forigi <group_names...>` — accepts multiple group names
- Root triple `forigi` left as-is (SPO-based, different semantics)

**Cross-module audit:**
- A-agento `stilo forigi`: issue filed (#58)
- A-organizi `todo forigi`: bug filed — accepts `list[str]` but resolves only first item (#24)
- A-workspace AGENTS.md: `forigi` Contract expanded with normative section

### Issue #14: Confirmation Prompt Mismatch (May 2026)
**Scope:** Fix confirmation prompt abbreviation casing + single-item `forigi` skip.

**Root cause:** A-core `confirm_action()` always showed uppercase first letter in prompt abbreviation (`[J/n]`) regardless of the `default` parameter value, violating terminal convention (uppercase = default option).

**A-core fix (PR #86):**
- `confirm_action()` now dynamically sets `prompt_abbr` casing based on `default`:
  - `default=True`: `[J/n]` (eo), `[Y/n]` (en), `[O/n]` (fr)
  - `default=False`: `[j/N]` (eo), `[y/N]` (en), `[o/N]` (fr)
- 6 new tests verifying all 3 locales × 2 default values

**A-semantika fix (this PR):**
- `nodo forigi`, `predikato forigi`, `predikat-grupo forigi`: skip confirmation when `len(resolved) == 1` (user already specified exact item)
- Multi-item (2+) keeps existing preview table + `[j/N]` prompt
- Root triple `forigi` unchanged (single-arc deletion is irreversible, no undo)
- 3 new CLI tests for single-item skip

**Bonus finding:** `A-lien` calls `confirm_action(..., abort=True)` but function has no `abort` param — needs separate issue.

### Issue #25: Code Review Round 3 — Code Quality & Orphan Prevention (May 2026)

**Scope:** 6 fixes from third code review round. 254 tests total (247 existing + 6 new + 1 trim).

| Fix | Severity | File | Description |
|-----|----------|------|-------------|
| F1 | Medium | `_cli_rubujo.py` | Removed dead `node_svc` parameter from `_resolve_trash_node()` |
| F2 | Medium | `_cli_nodo.py` | Pre-resolve arc targets before node creation to prevent orphans on ambiguous `--tipo`/`--superklaso` prefixes |
| F3 | Medium | `_triple_service.py` | Replaced hardcoded `_KNOWN_PREFIXES` tuple with extensible `_PREFIX_URIS` dict; added `register_prefix()`; Turtle export now emits dynamic `@prefix` declarations |
| F4 | Low | `_cli_modify.py` | No-op modifi (same old/new values) skips delete+insert cycle — preserves `kreita_je` |
| F5 | Low | `_node_service.py` | `create()` now catches `sqlite3.IntegrityError` instead of broad `Exception` with string matching |
| F6 | Low | `tests/test_cli_rubujo.py` | 6 new tests for interactive confirm paths in `rubujo` commands without `-y` |

### Issue #26: Code Review Round 4 — FK Messages, FTS5 Keywords, LIKE Escaping (May 2026)

**Scope:** 8 fixes from fourth code review round. 266 tests total (243 existing + 23 new).

| Fix | Severity | File | Description |
|-----|----------|------|-------------|
| F1 | Medium | `_triple_service.py` | FK violation masked as "already exists" — validate FK references explicitly before INSERT so subject/predicate/object errors show accurate messages |
| F2 | Medium | `_predicate_service.py` | Add COLLATE NOCASE + LIKE escape (%/_) to predicate search for case-insensitive matching and wildcard safety |
| F3 | Medium | `_node_service.py` | FTS5 keywords (AND/OR/NOT/NEAR/COLUMN) were being stripped — now lowercased and treated as regular content terms |
| F4 | Low | `_cli_nodo.py` | Non-existent --tipo/--superklaso targets silently dropped — now warns user via `warning()` |
| F5 | Low | `_cli_rubujo.py` | malplenigi count used `len(items)` from before deletion — now uses actual return value |
| F6 | Low | `_cli_rubujo.py` | Short node IDs (≤8 chars) were needlessly truncated in rubujo ls output |
| F7 | Low | `_cli_nodo.py` | Error handling string-matched generic `Exception` — now catches `sqlite3.IntegrityError` specifically |
| F8 | Low | `_predicate_service.py` | LIKE wildcards `%` and `_` in user queries acted as wildcards — now escaped for literal matching |

### Issue #27: Code Review Round 5 — Prefix Isolation, Dead Code, Exception Handling (May 2026)

**Scope:** 3 fixes + 1 monolith split from fifth code review round. 274 tests total (266 existing + 8 new).

| Fix | Severity | File | Description |
|-----|----------|------|-------------|
| Q1 | Low | `_triple_service.py` | `_PREFIX_URIS` moved from class-level to instance-level (`self._prefix_uris`) to prevent shared mutable state from `register_prefix()` |
| Q2 | Low | `_cli_nodo.py` | Removed dead `if isinstance(defns, dict) else []` branch in `vidi()` — `defns` is always a `dict` |
| Q3 | Med | `_cli_nodo.py` | `_ensure_predicate()` caught broad `ValueError` with string matching — changed to explicit `(ValueError, sqlite3.IntegrityError)` |
| Split | — | `_cli_nodo.py` → `_cli_helpers.py` | Moved `ensure_predicate()` to `_cli_helpers.py`; `_cli_nodo.py` reduced from 521 to 499 lines |

**Tests added:**
- `TestTripleServicePrefixIsolation` (2 tests) — custom prefix isolation between instances + default prefixes present
- `TestNodoVidiDefinitions` (3 tests) — vidi with definitions, without definitions, default empty definitions
- `TestEnsurePredicate` (3 tests) — creates new predicate, handles duplicate silently, re-raises other errors

### Issue #28: Code Review Round 6 — Turtle Export, Code Quality & Monolith Split (May 2026)

**Scope:** 8 fixes from sixth code review round. 277 tests total (274 existing + 3 new).

| Fix | Severity | File | Description |
|-----|----------|------|-------------|
| R1a | High | `_triple_service.py` → `_triple_turtle.py` | Turtle export now includes nodes without triples as `rdfs:label` triples (originally as comments, upgraded to standard RDF in Issue #34) |
| R1b | High | `_triple_turtle.py` | Node IDs starting with digits now emit full URIs `<...>` instead of invalid Turtle prefixed names like `:1234` |
| R1c | Low | `_triple_turtle.py` | Removed trailing blank lines from Turtle output |
| A2/A3 | High | `_preview.py` | Consolidated `resolve_node_label()` with `NodeService.get_display_label()` — eliminated 30 lines of duplicate eo→en→first fallback logic |
| Q5 | Med | `_cli_nodo.py` | Fixed type annotation: `arc_templates: list[dict]` → `list[tuple[str, str]]` |
| Q3 | Med | `_triple_service.py` | `params.append(str(limit))` → `params.append(limit)` — avoid fragile string coercion |
| B4 | Med | `_triple_search.py` | Added `warning()` when `resolve_objects()` falls back to literal mode (prevents silent mistyped-label confusion) |
| Q2 | Med | `_cli_predikato.py` | Consolidated nested `if not results` checks to clarify control flow |
| Q4 | Low | `_cli_rubujo.py` | `_resolve_trash_node()` now imports `get_db()` directly instead of accessing via `triple_svc.db` (layering fix) |
| Q6 | Low | `_predicate_group_service.py` | Removed manual duplicate check in `add_member()` — now relies on UNIQUE constraint + `IntegrityError` catch |
| Split | — | `_triple_service.py` → `_triple_turtle.py` | Extracted Turtle export logic (165 lines) to keep `_triple_service.py` under 500 lines (516→388) |

**Tests added:**
- `test_export_turtle_nodes_without_triples_in_comments` — orphan nodes appear as Turtle comments
- `test_export_turtle_digit_prefix_uses_full_uri` — digit-prefixed node IDs use `<...>` syntax
- `test_export_turtle_no_trailing_blank_lines` — output does not end with blank lines

### Issue #29: Code Review Findings Round 7 — B3/RDF-G3/M1 + Monolith Split (May 2026)

**Scope:** 3 fixes from seventh code review round + monolith test file split. 285 tests total
(277 existing + 8 new).

| Fix | Severity | File | Description |
|-----|----------|------|-------------|
| B3 | Low | `_cli_helpers.py` | `--lingvo` / `--unuo` without type flag now raises error + `typer.Exit(1)` instead of just warning. Prevents silent creation of wrong triple type. |
| RDF-G3 | Med | `_triple_turtle.py` | Unknown namespace predicates (e.g. `wdt:P1082`) now emit as full URIs `<wdt:P1082>` instead of concatenating with `base_uri`. Known prefixes (`rdf:`, `rdfs:`, `xsd:`, `owl:`) still emit prefixed names. |
| M1 | Low | `_cli_predikat_grupo.py` | `predikat-grupo modifi` now supports prefix matching with disambiguation. Exact match tried first, then prefix (LIKE) match. Ambiguous prefixes list all matches. Non-existent prefixes show "not found". |

**Monolith split:**
- `tests/test_edge_cases.py` (857 lines) → 10 focused test files (max ~140 lines each)
- `tests/test_cli.py` (794 lines) → 8 focused test files (max ~237 lines each)
- `tests/test_storage.py` (594 lines) → 3 focused test files (max ~358 lines each)

**Tests added:**
| Test | Area | File |
|------|------|------|
| `test_aldoni_lingvo_without_str_exits_error` | B3 | test_cli_type_flags.py |
| `test_aldoni_unuo_without_int_or_float_exits_error` | B3 | test_cli_type_flags.py |
| `test_export_turtle_unknown_namespace_as_full_uri` | RDF-G3 | test_cli_export.py |
| `test_export_turtle_known_prefix_still_works` | RDF-G3 | test_cli_export.py |
| `test_modifi_exact_name` | M1 | test_predicate_groups.py |
| `test_modifi_prefix_match_one` | M1 | test_predicate_groups.py |
| `test_modifi_prefix_ambiguous` | M1 | test_predicate_groups.py |
| `test_modifi_nonexistent_prefix` | M1 | test_predicate_groups.py |

### Issue #31: Code Review Round 8 — B3/B2/Q1 Fixes (May 2026)

**Scope:** 3 fixes from eighth code review round. 295 tests total (285 existing + 10 new).

| Fix | Severity | File | Description |
|-----|----------|------|-------------|
| B3 | Medium | `_cli_rubujo.py` | Added `COLLATE NOCASE` to `_resolve_trash_node()` for case-insensitive trash lookup |
| B2 | Low | `_triple_search.py` | Suppressed spurious fallback warning for obvious literals (numeric, multi-word, quoted strings) |
| Q1 | Low | `_preview.py` | De-duplicated `resolve_predicate_label()` by delegating to `storage.label_from_json()` — removed ~15 lines of duplicated eo→en→first fallback logic |

**Tests added (10):**
| Test | Fix | File |
|------|-----|------|
| `test_rubujo_restore_case_insensitive` | B3 | test_cli_rubujo.py |
| `test_rubujo_forigi_case_insensitive` | B3 | test_cli_rubujo.py |
| `test_numeric_literal_suppresses_warning` | B2 | test_triple_search.py |
| `test_multi_word_literal_suppresses_warning` | B2 | test_triple_search.py |
| `test_quoted_string_suppresses_warning` | B2 | test_triple_search.py |
| `test_single_word_non_numeric_still_warns` | B2 | test_triple_search.py |
| `test_returns_eo_label` | Q1 | test_preview_helpers.py |
| `test_returns_predicate_id_when_no_label` | Q1 | test_preview_helpers.py |
| `test_returns_predicate_id_when_not_found` | Q1 | test_preview_helpers.py |
| `test_falls_back_to_en_when_no_eo` | Q1 | test_preview_helpers.py |

### Issue #34: Standard `rdfs:label` in Turtle Export (May 2026)

**Scope:** Replace raw-JSON Turtle comments with standard `rdfs:label` triples.

**Problem:** Turtle export was dumping node labels as raw JSON comments:
```turtle
#   :Hundo  {"eo": "Hundo", "en": "Dog"}
```
This is not valid RDF — consumers can't parse labels programmatically.

**Fix:** Every node's `etikedoj` JSON is now emitted as standard W3C RDFS `rdfs:label` triples with language tags:
```turtle
:HUNDO
    rdf:type :KATO ;
    rdfs:label "Hundo"@eo,
               "Dog"@en .
```

**Changes:**
| File | What |
|------|------|
| `_triple_turtle.py` | Added `_build_label_map()` — parses etikedoj JSON for all nodes |
| `_triple_turtle.py` | Added `_append_label_lines()` — emits rdfs:label in comma-separated Turtle format |
| `_triple_turtle.py` | `export_turtle()` now calls `_append_label_lines()` for each subject before the flush |
| `_triple_turtle.py` | Nodes without outgoing triples now emit proper `rdfs:label` nodes instead of comments |
| `tests/test_triples.py` | Updated `test_export_turtle_nodes_without_triples_in_comments` → renamed to `_still_get_rdfs_label`, checks `rdfs:label` instead of `#` |

**Tests:** 295 total (unchanged count, 1 test updated).

### Upstream Dependencies
- A-core wikidata extraction: https://github.com/Ron-RONZZ-org/A-core/issues/9
- A-core get_property_details: https://github.com/Ron-RONZZ-org/A-core/issues/82
- A-core timeout parameter: https://github.com/Ron-RONZZ-org/A-core/issues/83
