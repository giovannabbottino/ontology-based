# Analyze API

## `GET /health`

Checks both external dependencies required by the ontology-based service:

- `ollama`: calls Ollama `/api/tags` and verifies that the configured model is installed;
- `wikidata_mcp`: initializes the streamable-HTTP MCP session and discovers the configured tools.

The endpoint returns `200` only when both components report `status: ok`. Otherwise it
returns `503`.

Example:

```json
{
  "ollama": {
    "status": "ok",
    "model": "llama3.1:8b"
  },
  "wikidata_mcp": {
    "status": "ok",
    "url": "https://wd-mcp.wmcloud.org/mcp/",
    "tools": [
      "search_items",
      "get_instance_and_subclass_hierarchy"
    ]
  }
}
```

Tool discovery is cached in the MCP client after the first successful request.

## `POST /analyze`

Builds an ontology-grounded RDF/Turtle graph. The service gives the configured Ollama
model a prompt and the restricted Wikidata MCP tool schemas, executes the requested
tool calls, returns their results to the model, and validates the final Turtle.

### Request body

```json
{
  "text": "Alan Turing worked at Bletchley Park during World War II.",
  "idempotence_key": "request-123",
  "prompt_name": "prompts/ontology-few-shot.txt",
  "system_prompt_name": "system/knowledge_graph.txt",
  "max_rdf_attempts": 3
}
```

| Field | Required | Description |
|---|---:|---|
| `text` | yes | Non-empty source text. Leading and trailing whitespace is removed. |
| `idempotence_key` | no | String used to correlate all JSONL events for this request. A UUID is generated when omitted. |
| `prompt_name` | no | Prompt path below `prompt/`; defaults to `DEFAULT_PROMPT_NAME`. |
| `system_prompt_name` | no | System-prompt path below `prompt/`; defaults to `DEFAULT_SYSTEM_PROMPT_NAME`. |
| `max_rdf_attempts` | no | Integer number of RDF generation attempts, clamped to 1–3. Default: 3. |

Prompt paths cannot escape the local `prompt/` directory.

### Processing behavior

1. Load the selected system and few-shot prompts.
2. Replace `${USER_TEXT}` or `${Text_TEXT}` with the request text. If neither marker is
   present, append a `User:`/`Assistant:` turn.
3. Discover the allowlisted Wikidata MCP tools and convert their JSON Schemas to Ollama
   function-tool definitions.
4. Send the conversation and tools to Ollama `/api/chat` with `stream:false`.
5. Execute every returned tool call through MCP `tools/call` and append its result as a
   `tool` message.
6. Execute at most `MAX_TOOL_CALLS` calls, truncating each result passed back to the
   model to `MAX_TOOL_RESULT_CHARS` characters.
7. Repeat until Ollama returns a final textual answer or `MAX_TOOL_ROUNDS` is exhausted.
7. When `REQUIRE_WIKIDATA_MCP=true`, remind a model that answers without a tool call once;
   reject the request if it again answers without using MCP.
8. Extract Turtle from the final answer and validate it strictly with
   `rdflib.Graph.parse(format="turtle")`.
9. If the RDF remains invalid and attempts remain, append parser feedback to the same
   conversation. A successful MCP call does not need to be repeated during RDF regeneration.

The service exposes only the tools in `WIKIDATA_MCP_TOOLS`. The default allowlist contains
`search_items` and `get_instance_and_subclass_hierarchy`; arbitrary statements and SPARQL
execution are therefore outside this ablation.

### Success response

```json
{
  "text": "Alan Turing was a human.",
  "rdf": "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n...",
  "prompt_name": "prompts/ontology-few-shot.txt",
  "system_prompt_name": "system/knowledge_graph.txt",
  "source_attribution": "Source: Wikidata MCP",
  "mcp_calls": [
    {
      "name": "search_items",
      "arguments": {"query": "Alan Turing"},
      "result": "Q7251: Alan Turing — English computer scientist (1912–1954)"
    },
    {
      "name": "get_instance_and_subclass_hierarchy",
      "arguments": {"entity_id": "Q7251", "max_depth": 2},
      "result": "{...}"
    }
  ]
}
```

`mcp_calls` is an audit trail in execution order. Each stored result is limited to 6,000
characters; the complete result is still passed to the model during the request.

### RDF acceptance criteria

The returned candidate must:

- be non-empty, valid Turtle;
- contain at least one triple;
- contain at least one predicate other than `rdfs:label`.

No local syntax repair, statement salvage, alternative data source, or substitute graph is
used. Invalid output is accepted only if a later attempt through the same LLM conversation
returns valid Turtle.

### Error responses

| Status | Cause |
|---:|---|
| `400` | Body is not a JSON object, `text` is absent/blank, or request field types are invalid. |
| `404` | Selected prompt file does not exist. |
| `422` | No valid RDF was obtained after the configured attempts. |
| `502` | Ollama/MCP request failed, an MCP tool was invalid, the model skipped required MCP use, or the tool-round limit was exceeded. |
| `504` | An external request timed out. |

## Logs

Every Ollama chat response is appended to `OLLAMA_CSV_PATH`. The CSV contains the model,
complete message history for that call, textual response, structured tool calls, and
creation timestamp. Request lifecycle, LLM/MCP activity, and RDF validation are also
written as JSON Lines to `ANALYZE_LOG_PATH`, correlated by `idempotence_key`. Logging is
best-effort and does not fail an analysis if the log file cannot be written.
