# A-semantika Code Review Findings

## Summary
A-semantika is a well-structured semantic triple store plugin for the A-ecosystem. The codebase demonstrates strong adherence to AGENTS.md standards, good architectural patterns, and comprehensive test coverage. However, there are several issues to address around error handling, edge cases, and potential bugs.

## Key Findings

### CRITICAL ISSUES
1. **Turtle Export Bug** (_triple_service.py:export_turtle)
   - Line 263: Incorrect Turtle formatting with trailing semicolons
   - The logic to replace trailing `;` with `.` is flawed
   - Will produce invalid Turtle syntax

2. **FTS5 Compatibility Issue** (_node_service.py:_remove_from_fts)
   - Workaround for SQLite 3.50+ is good, but needs testing
   - The generated SQL uses string interpolation for table name (safe here, but worth noting)

3. **Missing Predicate Validation** (_cli_triples.py:aldoni)
   - No validation that predicate exists before creating triple
   - Will fail with FK constraint error, but error message is generic

### HIGH PRIORITY ISSUES
1. **Ambiguous UUID Prefix Resolution** (_node_service.py:resolve_uuid_prefix)
   - Raises ValueError on ambiguous prefix, but callers don't always handle it
   - _cli_nodo.py:aldoni catches ValueError but doesn't distinguish between ambiguous vs not found

2. **Race Condition in _ensure_predicate** (_cli_nodo.py)
   - Multiple concurrent `nodo aldoni` calls with same shortcuts could create duplicate predicates
   - The `pass` on ValueError silently ignores all errors, not just duplicates

3. **Incomplete Transaction Handling** (_cli_triples.py:modifi)
   - Uses raw SQL with transaction context, but doesn't validate FK constraints
   - Could leave database in inconsistent state if new predicate doesn't exist

### MEDIUM PRIORITY ISSUES
1. **Label Extraction Inconsistency** (storage.py vs _node_service.py)
   - Two separate implementations of label extraction logic
   - Should be unified to prevent divergence

2. **Missing Null Checks** (_preview.py:resolve_node_label)
   - Calls node_svc.resolve_uuid_prefix() which can raise ValueError
   - Not all callers handle this exception

3. **Wikidata Timeout Defaults** (_wikidata_helper.py)
   - 5s search timeout may be too aggressive for slow networks
   - 10s details timeout is reasonable but not configurable

4. **Test Coverage Gaps**
   - No tests for UUID prefix ambiguity handling
   - No tests for concurrent operations
   - Limited error path testing in CLI

### CODE QUALITY ISSUES
1. **Duplicate Imports** (_cli_triples.py)
   - Lines 52, 62: `from A import warning as _warn` imported twice in same function
   - Should import once at top

2. **Inconsistent Error Messages** 
   - Some use tr_multi(), some use plain strings
   - _cli_predikato.py:vidi uses plain f-strings for output

3. **Magic Strings**
   - "rdf:type", "rdfs:subClassOf", "owl:disjointWith", "owl:inverseOf" hardcoded in multiple places
   - Should be constants

4. **Unused Variable** (_cli_nodo.py:aldoni)
   - Line 155: `result` variable assigned but never used

### SECURITY CONCERNS
1. **SQL Injection Risk** (_cli_triples.py:modifi, line 259-268)
   - Uses raw SQL with parameterized queries (good)
   - But direct string interpolation in DELETE/INSERT (actually safe with params, but worth reviewing)

2. **File Write Without Validation** (_cli_triples.py:eksporti)
   - No validation of output path (could write to system files)
   - Should validate path is within expected directory or use safe defaults

3. **Wikidata API Timeout** 
   - Network requests have timeouts (good)
   - But no rate limiting or retry logic

### PERFORMANCE CONSIDERATIONS
1. **FTS5 Search Fallback** (_node_service.py:search)
   - Falls back to LIKE if FTS returns nothing
   - Could be slow on large datasets
   - Consider adding LIMIT to FTS query

2. **No Pagination** 
   - All list/search commands use LIMIT but no offset/cursor support
   - Could be problematic for large datasets

3. **Denormalization Overhead** (_node_service.py)
   - Every node update re-indexes FTS
   - Could be slow for bulk operations

### BEST PRACTICES VIOLATIONS
1. **AGENTS.md Compliance**
   - ✅ Uses tr_multi() for user-facing strings
   - ✅ Uses error()/info() for output
   - ✅ Type hints on public functions
   - ✅ Docstrings on public functions
   - ✅ Tests with autouse fixture
   - ✅ WAL mode enabled
   - ✅ FTS5 for search
   - ✅ Imports from A
   - ✅ box=BOX_SIMPLE on tables
   - ✅ UUID primary keys
   - ⚠️ Some error messages not in tr_multi()
   - ⚠️ No undo/trash for triples (intentional, but worth noting)

2. **Missing Documentation**
   - No docstrings for private functions (_extract_label_text, etc.)
   - CLI help strings are good but could be more detailed

3. **Test Isolation**
   - ✅ Good autouse fixture
   - ✅ Monkeypatches data_dir
   - ✅ Resets singletons
   - ⚠️ No tests for Wikidata network failures (mocked, but incomplete)

## Recommendations

### Immediate Fixes (P0)
1. Fix Turtle export formatting bug
2. Add predicate existence validation before triple creation
3. Fix race condition in _ensure_predicate

### Short Term (P1)
1. Unify label extraction logic
2. Add proper exception handling for UUID prefix resolution
3. Extract magic strings to constants
4. Add comprehensive error path tests

### Medium Term (P2)
1. Add pagination support for large datasets
2. Implement rate limiting for Wikidata API
3. Add path validation for file exports
4. Consider bulk operation optimization

### Long Term (P3)
1. Add undo/trash support for triples (if needed)
2. Implement query optimization for complex triple patterns
3. Add performance benchmarks
4. Consider caching for frequently accessed nodes
