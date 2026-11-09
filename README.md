# Ontology-based Knowledge Graph API

Flask API that extracts RDF graphs from text using Ollama and Wikidata entity and hierarchy lookups through MCP. Requires Python 3.12, Ollama with `llama3.1:8b`, and access to the MCP endpoint.

## Run

Copy `.env.example` to `.env` in the project root and adjust the file. The application loads `.env` on startup; the local file is not tracked by Git.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ollama pull llama3.1:8b
python -m ontology_based
```

The API runs at `http://127.0.0.1:5100`. Use `GET /health` to check Ollama and Wikidata MCP.

## Analyze

```powershell
$body = @{ text = "Alan Turing was a human."; max_rdf_attempts = 3 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5100/analyze" -ContentType "application/json" -Body $body
```

The LLM returns `{"rdf": "<Turtle string>"}`. The API validates the JSON, Turtle, and prefixes, then returns `rdf` with the input text, prompt names, and MCP call history. Empty or invalid responses receive feedback and may be regenerated, up to three attempts in total, without repeating lookups. If all attempts fail, the API returns HTTP 422.

## Configuration and logs

All settings are listed in [.env.example](.env.example); edit local values in `.env`. Defaults are seed 42, temperature 0, top_k 1, top_p 1, min_p 0, a 2048-token limit for final generation, and a 300-second timeout per Ollama call. Tool calls have a separate 256-token limit.
Logs are written to `logs/ollama_responses.jsonl` and `logs/analyze_log.jsonl`, with one JSON object per line. Messages and tool calls are stored as nested JSON values. The optional `request_id` field correlates events; it does not deduplicate requests.

## Verify

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m pyright
```

Details: [API](docs/analyze.md), [run guide](docs/how-to-run.md), [prompts](docs/prompt.md), and [tests](docs/how-to-test.md).
