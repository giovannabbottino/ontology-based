# Ontology-based Knowledge Graph Construction API

Flask API for the ontology-based ablation between `prompt-based` and
`hybrid-pipelines`. It keeps the prompt-driven RDF generation flow, but lets the
LLM consult a restricted Wikidata MCP tool set before producing Turtle.

## Ablation boundary

| Variant | Prompt | Wikidata grounding | Explicit extraction/relationship pipeline |
|---|---:|---:|---:|
| `prompt-based` | yes | no | no |
| `ontology-based` | yes | entity search + instance/subclass hierarchy through MCP | no |
| `hybrid-pipelines` | yes | entities, statements, and relationships | yes |

The default MCP allowlist contains only `search_items` and
`get_instance_and_subclass_hierarchy`. This keeps the experiment ontology-focused:
it does not reproduce the hybrid pipeline's statement and direct-relationship retrieval.

The system and few-shot prompts use the same generic core and the same two
RDFLib-validated examples as `prompt-based`. Ontology-specific behavior is isolated in
dedicated Wikidata-grounding blocks that restrict tools and QIDs to the current input.

## Quick start

Requirements: Python 3.12, Ollama with `llama3.1:8b`, and outbound
HTTPS access to the configured Wikidata MCP endpoint.

```bash
ollama pull llama3.1:8b
python -m pip install -e ".[dev]"
python -m ontology_based
```

In another terminal:

```bash
curl -X POST http://127.0.0.1:5100/analyze \
  -H "Content-Type: application/json" \
  -d '{"text":"Alan Turing worked at Bletchley Park.","max_rdf_attempts":3}'
```

With `REQUIRE_WIKIDATA_MCP=true`, a successful request must include at least one
allowlisted Wikidata tool call.

## Flow

1. Load the system and few-shot prompt and insert the input text.
2. Discover the allowed tools from the Wikidata streamable-HTTP MCP endpoint.
3. Send the prompt and MCP tool schemas to Ollama `/api/chat`.
4. Execute requested tool calls and return their results to the model.
5. Validate the final Turtle with `rdflib`, retrying an invalid result up to three times.

`REQUIRE_WIKIDATA_MCP=true` is the default. A request fails if the model returns an
answer without consulting Wikidata, which prevents silently turning this ablation into
the prompt-only baseline.

## API

### `GET /health`

Checks Ollama/model availability and MCP initialization/tool discovery. It returns `200`
only when both dependencies are available.

### `POST /analyze`

```json
{
  "text": "Alan Turing worked at Bletchley Park during World War II.",
  "max_rdf_attempts": 3
}
```

The response includes the RDF and an audit trail of MCP calls:

```json
{
  "text": "Alan Turing worked at Bletchley Park during World War II.",
  "rdf": "@prefix ...",
  "source_attribution": "Source: Wikidata MCP",
  "mcp_calls": [
    {"name": "search_items", "arguments": {"query": "Alan Turing"}, "result": "..."}
  ]
}
```

## Configuration

| Variable | Default |
|---|---|
| `DEFAULT_PROMPT_NAME` | `prompts/ontology-few-shot.txt` |
| `DEFAULT_SYSTEM_PROMPT_NAME` | `system/knowledge_graph.txt` |
| `WIKIDATA_MCP_URL` | `https://wd-mcp.wmcloud.org/mcp/` |
| `WIKIDATA_MCP_TOOLS` | `search_items,get_instance_and_subclass_hierarchy` |
| `WIKIDATA_LANGUAGE` | `en` |
| `WIKIDATA_TIMEOUT_SECONDS` | `60` |
| `WIKIDATA_USER_AGENT` | `ontology-based-agent/1.0` |
| `REQUIRE_WIKIDATA_MCP` | `true` |
| `MAX_TOOL_ROUNDS` | `8` |
| `MAX_TOOL_CALLS` | `4` |
| `MAX_TOOL_RESULT_CHARS` | `1500` |
| `OLLAMA_API_URL` | `http://localhost:11434` |
| `OLLAMA_MODEL` | `llama3.1:8b` |
| `OLLAMA_TIMEOUT_SECONDS` | `300` |
| `OLLAMA_TOOL_NUM_PREDICT` | `256` |
| `OLLAMA_CSV_PATH` | `data/ollama_responses.csv` |
| `ANALYZE_LOG_PATH` | `data/analyze_log.jsonl` |

The standard Ollama generation variables (`OLLAMA_SEED`, `OLLAMA_TEMPERATURE`,
`OLLAMA_TOP_K`, `OLLAMA_TOP_P`, `OLLAMA_MIN_P`, `OLLAMA_STOP`, `OLLAMA_NUM_CTX`, and
`OLLAMA_NUM_PREDICT`) are also supported.

The configured model must return structured tool calls for the ontology flow to complete.
The default is `llama3.1:8b`, matching the other experimental pipelines and providing
native Ollama tool-call support.

The tool-call and result-size limits keep tool conversations and large hierarchy responses
from consuming the model context and causing long-running requests.
`OLLAMA_TOOL_NUM_PREDICT` applies only while tools are available; final Turtle generation
continues to use `OLLAMA_NUM_PREDICT`.

## Run and test

```bash
python -m pip install -e .[dev]
python -m ontology_based
python -m pytest
python -m ruff check .
python -m pyright
```

The local service listens on `http://127.0.0.1:5100`.

The supported Python version and Docker image are both Python 3.12.

## Documentation

- [API contract](docs/analyze.md)
- [Prompt design](docs/prompt.md)
- [Run guide](docs/how-to-run.md)
- [Test guide](docs/how-to-test.md)
- [Sequence diagram source](docs/seq/analyze.puml)
