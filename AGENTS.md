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
├── _cli_triples.py        # Root triple CLI: aldoni, forigi
├── _node_service.py       # NodeService (CRUDService + FTS5)
├── _predicate_service.py  # PredicateService (CRUDService + LIKE search)
├── _predicate_group_service.py  # PredicateGroupService (CRUDService + member mgmt)
├── _triple_search.py      # Triple search by partial labels (Issue #8 R2)
├── _triple_service.py     # TripleService (custom, non-CRUDService)
├── _preview.py            # Rich table preview helpers
└── data/
    └── storage.py         # Schema DDL, get_db(), init_db(), get_service() singletons
tests/
├── conftest.py               # autouse isolation fixture
├── test_cli.py               # CLI integration (includes Wikidata tests)
├── test_nodes.py
├── test_predicates.py
├── test_predicate_groups.py
├── test_triple_search.py  # Triple search unit tests (Issue #8 R2)
├── test_triples.py
├── test_storage.py
└── test_wikidata_helper.py   # Wikidata helper unit tests
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

### Issue #15: Ungraceful Error Handling for UNIQUE Constraints (May 2026)

**Fixed**: Raw `IntegrityError` tracebacks in `nodo aldoni` and `nodo forigi` are now caught and shown as user-friendly messages.

| Before | After |
|--------|-------|
| `$ A semantika nodo aldoni SPACO` → raw traceback `IntegrityError: UNIQUE constraint failed: nodes.uuid` | `[✗] Nevalida UUID-formato...` (UUID validated before any DB write) |
| `$ A semantika nodo aldoni <existing-uuid>` → raw traceback `IntegrityError` | `[✗] Node with UUID '...' already exists. Use 'A semantika nodo modifi ...' to modify it.` |
| `$ A semantika nodo forigi <uuid>` (corrupted trash) → `Eraro forigante ...: UNIQUE constraint failed: nodes_rubujo.uuid` | `Nodo ... jam estas en la rubujo` (or handled by A-core C4) |

**5 changes across 2 repos:**

| Change | File | What |
|--------|------|------|
| **C1** | `_cli_nodo.py:aldoni()` | UUID format validation — rejects non-UUID strings via regex before any DB write |
| **C2** | `_node_service.py:create()` | Catches `IntegrityError` on INSERT → raises `ValueError` with "already exists" guidance |
| **C3** | `_cli_nodo.py:aldoni()` | Catches `ValueError` from service → shows `error()` + clean `typer.Exit(1)` |
| **C4** | `A-core/service.py:_move_to_trash()` | `INSERT` → `INSERT OR REPLACE` — prevents trash-duplicate at source (separate A-core PR) |
| **C5** | `_cli_nodo.py:forigi()` | Filters raw `"UNIQUE constraint failed"` → friendly "already in trash" message |

**5 new tests** in `test_nodes.py` and `test_edge_cases.py` covering:
- Invalid UUID format CLI rejection
- Duplicate UUID with friendly error message
- Auto-generated UUID still works
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
- `nodo forigi <uuids...>` — accepts multiple UUID prefixes
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

### Upstream Dependencies
- A-core wikidata extraction: https://github.com/Ron-RONZZ-org/A-core/issues/9
- A-core get_property_details: https://github.com/Ron-RONZZ-org/A-core/issues/82
- A-core timeout parameter: https://github.com/Ron-RONZZ-org/A-core/issues/83
