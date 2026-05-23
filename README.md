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

## Development

```bash
uv run pytest tests/ -v
```

## License

GPL-3.0-only
