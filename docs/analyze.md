# API

[README](../README.md) · [Run guide](how-to-run.md) · [Prompts](prompt.md)

## GET /health

Checks Ollama/model availability and Wikidata MCP. Returns 200 when both are available, otherwise 503.

## POST /analyze

### Request

```json
{"text": "Alan Turing was a human.", "max_rdf_attempts": 3, "request_id": "request-123"}
```

`text` is required and cannot be blank. `max_rdf_attempts` is an integer clamped to 1-3, defaulting to 3. `request_id` is an optional string for log correlation; a UUID is generated when omitted. `prompt_name` and `system_prompt_name` are optional paths restricted to the `prompt/` directory.

### Processing and response

The API queries Wikidata through MCP and asks the LLM for a JSON object containing only the `rdf` key with a Turtle string. The HTTP response includes `text`, `rdf`, `prompt_name`, `system_prompt_name`, `source_attribution`, and `mcp_calls` in execution order.
Turtle must declare the `rdfs`, `wd`, and `kg` prefixes with the namespaces specified in the prompts, contain triples, and include at least one relationship beyond `rdfs:label`. Valid content is returned without repair or reserialization. Syntax validation does not guarantee factual accuracy.
Invalid JSON, a missing key, empty RDF, missing/incorrect prefixes, or invalid Turtle triggers another attempt with feedback. There are at most three attempts in total, reusing completed lookups. Generation stops immediately on valid output.

### Status codes

| Status | Reason |
|---|---|
| 200 | Analysis completed. |
| 400 | Invalid request body or fields. |
| 404 | Prompt file not found. |
| 422 | Invalid RDF after all attempts are exhausted. |
| 502 | External failure, invalid tool, or MCP phase limit exceeded. |
| 504 | External call timed out. |


## Configuration and logs

Configure the application in `.env`, using [`.env.example`](../.env.example) as a reference. Logs are stored in `logs/`.
