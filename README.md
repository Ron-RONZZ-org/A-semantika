# A-semantika — Semantic Triple Store

Pure semantic-arc-based world modelling (RDF-style triple store) for fragmented,
machine-inferencable knowledge note-taking.

## Quick Start

```bash
# Install
uv pip install -e .

# Create a node
A semantika nodo aldoni -e "eo::Hundo" -e "en::Dog"

# Assert a triple
A semantika aldoni <node-uuid> rdf:type <type-uuid> --uri

# Search triples by partial labels
A semantika serci --subject Hundo --predicate tipo

# Delete with interactive picker (omit predicate/object)
A semantika forigi <node-uuid-prefix>

# Export to Turtle
A semantika eksporti
```

## Features

- **RDF-style triple store**: subject-predicate-object arcs with URI and literal support
- **Partial label search**: `serci` resolves UUID prefixes, FTS5 labels, and raw text
- **Interactive picker**: `forigi`/`modifi` without full args shows numbered selection menu
- **All commands use `--jes`** (Esperanto for "yes") with `-y`/`--yes` backward compat
- **Standard Turtle export** with multilingual `rdfs:label` support

## Turtle Export Format

The `eksporti` command exports the entire triple store to standard [Turtle (.ttl)](https://www.w3.org/TR/turtle/) format, compatible with any RDF parser.

### Example

```bash
# Export to stdout
A semantika eksporti

# Export to file
A semantika eksporti -o mydata.ttl
```

### Output Structure

**Input:**
```
nodo aldoni HUNDO -e "eo::Hundo" -e "en::Dog"
nodo aldoni KATO -e "eo::Kato" -e "en::Cat"
aldoni HUNDO rdf:type KATO --uri
```

**Output (Turtle):**
```turtle
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:HUNDO
    rdf:type :KATO ;
    rdfs:label "Hundo"@eo,
               "Dog"@en .

:KATO
    rdfs:label "Kato"@eo,
               "Cat"@en .
```

### Key Features

1. **Standard W3C Compliant**: Uses RDF namespace prefixes (`rdf:`, `rdfs:`, `xsd:`, `owl:`)
2. **Multilingual Labels**: Node `etikedoj` (labels) are exported as standard `rdfs:label` triples with language tags
3. **Proper Datatype Handling**: Typed literals use `xsd:` datatypes (integer, decimal, boolean, date, etc.)
4. **Automatic Prefix Expansion**: Node IDs starting with digits emit full URIs to ensure valid Turtle syntax
5. **POSIX Newline**: Output ends with a single newline character

### Triple Types

| Type | Turtle | Example |
|------|--------|---------|
| **URI Triple** | `subject predicate object .` | `:DOG rdf:type :ANIMAL .` |
| **String Literal** | `subject predicate "string"@lang .` | `:DOG rdfs:label "Hundo"@eo .` |
| **Typed Literal** | `subject predicate value^^type .` | `:AGE rdf:value 5^^xsd:integer .` |
| **Raw Label Node** | (appears as `rdfs:label`) | `:HUNDO rdfs:label "Hundo"@eo .` |

## Performance Notes

- **Bulk Triple Queries** (`get_by_nodes()`): O(1) SQL query instead of O(N) loops — used by `forigi` for batch deletion
- **Conditional FTS Rebuild**: `init_db()` only rebuilds full-text-search index if new predicates were added
- **Single COLLATE NOCASE Query**: Node lookups use unified case-insensitive matching in one query instead of fallback attempts

See `tests/test_perf_benchmarks.py` for detailed benchmarks.

## Development

```bash
# Run all tests
uv run pytest tests/ -v

# Run performance benchmarks
uv run pytest tests/test_perf_benchmarks.py -v -s

# Run specific test class
uv run pytest tests/test_triples.py::TestTripleAdd -v
```

## License

GPL-3.0-only
