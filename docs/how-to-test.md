# Tests

With the virtual environment active, install the development dependencies and run:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m pyright
```

The suite replaces Ollama and Wikidata with test doubles; no external services are required. Tests cover the `{"rdf": "..."}` contract, Turtle and prefixes, empty/invalid responses, the three-attempt limit, MCP evidence reuse, configuration, logs, and HTTP endpoints.
For manual testing, configure `.env` from `.env.example`, start the API, and follow the [README](../README.md) example. Runtime logs are stored in `logs/`.
