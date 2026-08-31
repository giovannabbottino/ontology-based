# How to run

## Requirements

- Python 3.12 for local execution;
- Ollama with a tool-capable model;
- network access to the configured Wikidata MCP endpoint.

The default model is `llama3.1:8b`, matching the other experimental pipelines and
supporting the structured tool calls required by the ontology-based flow.

## Environment variables

| Variable | Default |
|---|---|
| `DEFAULT_PROMPT_NAME` | `prompts/ontology-few-shot.txt` |
| `DEFAULT_SYSTEM_PROMPT_NAME` | `system/knowledge_graph.txt` |
| `OLLAMA_API_URL` | `http://localhost:11434` |
| `OLLAMA_MODEL` | `llama3.1:8b` |
| `OLLAMA_CSV_PATH` | `data/ollama_responses.csv` |
| `ANALYZE_LOG_PATH` | `data/analyze_log.jsonl` |
| `OLLAMA_TIMEOUT_SECONDS` | `660` |
| `OLLAMA_TOOL_NUM_PREDICT` | `256` |
| `WIKIDATA_MCP_URL` | `https://wd-mcp.wmcloud.org/mcp/` |
| `WIKIDATA_MCP_TOOLS` | `search_items,get_instance_and_subclass_hierarchy` |
| `WIKIDATA_LANGUAGE` | `en` |
| `WIKIDATA_TIMEOUT_SECONDS` | `60` |
| `WIKIDATA_USER_AGENT` | `ontology-based-agent/1.0` |
| `REQUIRE_WIKIDATA_MCP` | `true` |
| `MAX_TOOL_ROUNDS` | `8` |
| `MAX_TOOL_CALLS` | `4` |
| `MAX_TOOL_RESULT_CHARS` | `1500` |

Optional Ollama options are included only when set: `OLLAMA_SEED`,
`OLLAMA_TEMPERATURE`, `OLLAMA_TOP_K`, `OLLAMA_TOP_P`, `OLLAMA_MIN_P`,
`OLLAMA_STOP`, `OLLAMA_NUM_CTX`, and `OLLAMA_NUM_PREDICT`.

Use `.env.example` as the local configuration template. Do not add `get_statements` or
`execute_sparql` to the tool allowlist when reproducing the default ontology ablation.

## Docker Compose

From the repository root:

```powershell
docker compose up -d ollama
docker exec -it kg-ollama ollama pull llama3.1:8b
docker compose up --build -d ontology-based
```

Check dependencies:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5100/health"
```

Analyze text:

```powershell
$body = @{
  text = "Alan Turing worked at Bletchley Park during World War II."
  max_rdf_attempts = 3
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5100/analyze" `
  -ContentType "application/json" `
  -Body $body
```

Ollama logs are persisted under `ontology-based/data/` by the Compose volume.

## Local execution

Run from `ontology-based/`.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ollama pull llama3.1:8b
python -m ontology_based
```

Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull llama3.1:8b
python -m ontology_based
```

The local API listens on `http://127.0.0.1:5100`.

## Troubleshooting

- `missing_model`: pull the exact model shown by `/health`.
- Model returns no tool calls: confirm that the model supports tools and leave
  `REQUIRE_WIKIDATA_MCP=true` to avoid silently running the prompt-only baseline.
- MCP is unavailable: verify `WIKIDATA_MCP_URL`, outbound HTTPS, and the user agent.
- Tool-round limit exceeded: inspect `OLLAMA_CSV_PATH`; increase `MAX_TOOL_ROUNDS` only
  after checking for repetitive calls.
- Excessive tool calls or context growth: keep `MAX_TOOL_CALLS` and
  `MAX_TOOL_RESULT_CHARS` bounded; increasing them also increases Ollama latency.
- Tool-selection responses are verbose or slow: keep `OLLAMA_TOOL_NUM_PREDICT` lower
  than the final RDF `OLLAMA_NUM_PREDICT` budget.
- RDF validation fails: increase `max_rdf_attempts` up to 3 or make the prompt stricter.
- Timeout: tune `OLLAMA_TIMEOUT_SECONDS` and `WIKIDATA_TIMEOUT_SECONDS` independently.
