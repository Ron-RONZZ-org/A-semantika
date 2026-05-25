# Issue #39: Additional Code Review Round 15 Fixes (Q1-Q3)

## Background
After the initial Issue #39 commit (F1-F4 from code review round 15), a secondary
review uncovered 3 additional issues (Q1-Q3) that were addressed in commit `ae323d0`.

## Changes

### Q1: LIKE wildcard escaping in `_resolve_trash_node()`
- File: `_cli_rubujo.py:82-83`
- Symptom: Node IDs containing `_` or `%` acted as LIKE wildcards in trash prefix search
- Fix: Added `escaped = node_id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")` with `ESCAPE '\\'`
- Pattern matches `resolve_node_id_prefix()` in `_node_service.py`
- Tests: `test_rubujo_resolve_trash_node_underscore_matched_literally`, `test_rubujo_resolve_trash_node_percent_matched_literally`

### Q2: Rollback error masking in `create_node_arcs()`
- File: `_cli_helpers.py:413-417`
- Symptom: Rollback exceptions (e.g. `node_svc.delete()` failure) masked the original `ValueError`
- Fix: Wrapped rollback in `try/except (sqlite3.Error, ValueError)` with `warning()` logging
- Tests: `test_rollback_delete_failure_preserves_original_error`, `test_rollback_remove_by_node_failure_preserves_original_error`

### Q3: Rename `resolve_uuid_prefix` → `resolve_node_id_prefix`
- File: `_node_service.py:419` (definition) + 9 source files + 2 test files
- Rationale: Column was renamed from `uuid` to `node_id` in Issue #15; method name never updated
- Backward-compat `resolve_uuid_prefix()` alias with `DeprecationWarning`
- 370 tests total (+5 new, all pass)

## Relevant Files
- `src/A_semantika/_cli_rubujo.py` — Q1 fix
- `src/A_semantika/_cli_helpers.py` — Q2 fix
- `src/A_semantika/_node_service.py` — Q3 rename + backward-compat alias
- `src/A_semantika/_cli_modify.py`, `_cli_nodo.py`, `_cli_query.py`, `_cli_triples.py` — Q3 call sites
- `src/A_semantika/_preview.py`, `_triple_search.py`, `_node_helpers.py` — Q3 references
- `tests/test_cli_rubujo.py`, `tests/test_review_round15.py`, `tests/test_nodes.py`, `tests/test_search_helpers.py`
- `AGENTS.md` — documented
