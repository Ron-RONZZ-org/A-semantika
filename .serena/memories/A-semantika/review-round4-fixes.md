# Review Round 4 — Code Quality Fixes (May 2026)

## Summary
8 fixes applied in commit `e7fa636` (branch `fix/review-round4-code-quality`).
266 tests total (23 new, all passing).
Issue #26 (closed).

## Fixes

### F1: FK violation masked as "already exists" (Medium)
- **File:** `_triple_service.py:add()`
- **Before:** `INSERT OR IGNORE` suppressed FK violations → misleading "Triple already exists"
- **After:** Explicit FK validation (subject node, predicate, object URI node) before INSERT
- **Error messages:** "Subject node not found", "Predicate not found", "Object node not found"
- Duplicate PK still shows "Triple already exists"

### F2: COLLATE NOCASE + LIKE escape in PredicateService (Medium)
- **File:** `_predicate_service.py:search()`
- **Before:** `LIKE` without `COLLATE NOCASE` → case-sensitive; `%` and `_` treated as wildcards
- **After:** `LIKE ... COLLATE NOCASE` with `ESCAPE '\'`; user `%`/`_` escaped via `replace()`

### F3: FTS5 keywords treated as regular terms (Medium)
- **File:** `_node_service.py:search()`
- **Before:** FTS5 keywords (AND/OR/NOT/NEAR/COLUMN) stripped from query
- **After:** Lowercased and treated as regular content terms (e.g. "AND" → "and" which FTS5 indexes as text)

### F4: Arc target warning for non-existent --tipo/--superklaso (Low)
- **File:** `_cli_nodo.py:_resolve_arc_target()`
- **Before:** Silently returned None — user would think arc was created
- **After:** Calls `warning()` with trilingual message: "Arc target not found: {t} (skipped)"

### F5: empty_trash count accuracy (Low)
- **File:** `_cli_rubujo.py:malplenigi()`
- **Before:** `len(items)` from pre-deletion query
- **After:** Uses return value of `node_svc.empty_trash()`

### F6: Short node ID truncation (Low)
- **File:** `_cli_rubujo.py` (3 occurrences)
- **Before:** Always used `n.get("node_id", "?")[:8]`
- **After:** `nid[:8] if len(nid) > 8 else nid`

### F7: sqlite3 typed exceptions (Low)
- **File:** `_cli_nodo.py:forigi()`
- **Before:** `except Exception` + string matching for UNIQUE/FK
- **After:** `except sqlite3.IntegrityError` for UNIQUE/FK, `except Exception` for "malformed"

### F8: LIKE wildcard escaping (Low)
- **File:** `_predicate_service.py:search()`
- **Before:** `pattern = f"%{query}%"` — user `%`/`_` acted as LIKE wildcards
- **After:** `query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")` + `ESCAPE '\\'` in SQL

## Tests
- `test_triples.py`: 3 new tests for FK error message accuracy
- `test_predicates.py`: 4 new tests for case-insensitive search and LIKE escaping
- `test_edge_cases.py`: 8 new tests (FTS5 keywords + arc target warning)
- `test_cli_rubujo.py`: 2 new tests (count accuracy + short node ID display)
