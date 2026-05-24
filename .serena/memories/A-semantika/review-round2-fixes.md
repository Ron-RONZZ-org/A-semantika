# A-semantika Review Round 2 Fixes (June 2026)

## Status
✅ All 11 findings fixed. PR #24 merged via branch `fix/issue-21-22-23-turtle-cli-codequality`. All 227 tests pass.

## Issues Fixed

### #21: Turtle Export RDF Correctness
| Finding | Fix | File |
|---------|-----|------|
| `:rdf:type` instead of `rdf:type` (namespace prefix collision) | Added `_KNOWN_PREFIXES` constant + `_format_turtle_uri()` helper | `_triple_service.py` |
| Missing `@prefix owl:` declaration | Added to preamble | `_triple_service.py` |
| Incomplete literal escaping (no newline/tab escape) | Added `_escape_turtle_literal()` with \n, \r, \t | `_triple_service.py` |

### #22: CLI tr_multi and UI Consistency
| Finding | Fix | File |
|---------|-----|------|
| `info(f"ID: ...")` not in `tr_multi()` | Wrapped in `tr_multi()` | `_cli_predikato.py` |
| `info(f"Fonto: ...")` not in `tr_multi()` | Wrapped in `tr_multi()` | `_cli_predikato.py` |
| `"UUID"` header in `serci` table | Changed to `"ID"` | `_cli_nodo.py` |
| Redundant `from A import info as _info` | Removed, use module-level import | `_cli_predikato.py`, `_cli_predikat_grupo.py` |

### #23: Code Quality
| Finding | Fix | File |
|---------|-----|------|
| Non-atomic `exists()` + INSERT (race condition) | Replaced with `INSERT OR IGNORE` + check `rowcount` | `_triple_service.py` |
| `typer.BadParameter` outside callback | Changed to `error()` + `typer.Exit(1)` | `_cli_helpers.py` |
| Duplicate label extraction in 4+ places | Consolidated to `storage.label_from_json()` | Multiple files |
| N+1 query in predikat-grupo ls | Single `GROUP BY` query | `_cli_predikat_grupo.py` |
| 4x redundant UUID resolution in preview table | Pre-resolve subject node once | `_preview.py` |
