# Run guide

Use Python 3.12 and follow the [Run](../README.md#run) commands from the project root. Copy `.env.example` to `.env` before starting the API; adjust the model, endpoints, and limits in that file instead of exporting variables individually.
Ollama must be running with the model specified in `.env`. The API uses port 5100; `GET /health` returns 200 when Ollama and Wikidata MCP are available, or 503 if either dependency fails.
By default, analysis requires at least one MCP call and allows only entity search and hierarchy lookups. Disabling this requirement in `.env` also skips the lookup phase during analysis; the health check still checks both dependencies.
Log directories are created automatically. See `logs/ollama_responses.jsonl` for conversations and `logs/analyze_log.jsonl` for events correlated by `request_id`. The 300-second timeout applies per Ollama call, not per complete analysis.
