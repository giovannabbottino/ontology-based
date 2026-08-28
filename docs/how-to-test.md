# How to test

Tests are split into:

- `tests/unit/test_services.py`: MCP/Ollama orchestration, required MCP use, hierarchy
  workflow, strict RDF validation, and same-conversation retries;
- `tests/unit/test_wikidata_mcp_client.py`: MCP initialization, allowlist filtering,
  default language injection, tool execution, and UTF-8 handling;
- `tests/unit/test_prompts.py`: critical grounding and placeholder constraints;
- `tests/integration/test_app_requests.py`: Flask `/analyze` and `/health` contracts with
  stubbed external dependencies.

## Install development dependencies

Run from `ontology-based/` with Python 3.10–3.13:

```bash
python -m pip install -r requirements-dev.txt
```

## Full verification

```bash
python -m pytest
python -m ruff format --check .
python -m ruff check .
python -m pyright
```

## Focused runs

```bash
python -m pytest tests/unit/test_services.py
python -m pytest tests/unit/test_wikidata_mcp_client.py
python -m pytest tests/unit/test_prompts.py
python -m pytest tests/integration/test_app_requests.py
```

The automated suite does not require Ollama or network access; both external components
are replaced with test doubles.

## Optional live MCP smoke test

This read-only check initializes the hosted endpoint and lists the allowlisted tools:

```powershell
python -c "from ontology_based.infrastructure import WikidataMCPClient,WikidataMCPConfig; print(WikidataMCPClient(WikidataMCPConfig()).health())"
```

Expected tool names are `search_items` and `get_instance_and_subclass_hierarchy`. Live
tests are intentionally excluded from the default suite because remote data and service
availability can change independently of the code.

## Docker configuration check

From the repository root:

```bash
docker compose config --quiet
docker compose build ontology-based
```

The second command requires Docker Desktop or another Docker daemon to be running.
