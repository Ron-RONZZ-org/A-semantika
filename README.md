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

# Export to Turtle
A semantika eksporti
```

## Development

```bash
uv run pytest tests/ -v
```

## License

GPL-3.0-only
