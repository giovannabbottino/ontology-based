# Prompt documentation

The ontology-based service uses the prompt pair inherited conceptually from the
prompt-based baseline:

- `prompt/system/knowledge_graph.txt`
- `prompt/prompts/ontology-few-shot.txt`

Unlike the prompt-only baseline, these prompts instruct the model to obtain entity IDs
and classification evidence through the Wikidata MCP tools before producing Turtle.

## System prompt

The system prompt defines the model as an ontology-grounded structured-data assistant.
Its central rules are:

- call `search_items` for recognizable real-world entities;
- inspect selected QIDs with `get_instance_and_subclass_hierarchy` when classification
  matters;
- treat MCP results from the current request as the only authority for QIDs and ontology
  classes;
- never copy a QID from model memory or merely from a few-shot example;
- use hierarchy evidence for classifications without adding unrelated Wikidata facts;
- use `kg:` resources when MCP does not resolve a concept;
- return only valid Turtle with the declared prefixes;
- label every subject/object resource and prefer traversable entity-to-entity triples.

Tool calls are structured Ollama messages and therefore do not appear in the final Turtle.

## Ontology few-shot prompt

The few-shot prompt retains the task structure, prefix vocabulary, RDF constraints, and
three transformation examples from `prompt-based`. It adds the following grounding rules:

- use Wikidata MCP before generating RDF;
- resolve entities with `search_items`;
- inspect the instance/subclass hierarchy of selected items;
- authorize only QIDs actually returned by MCP during the current request;
- interpret QIDs in examples as formatting demonstrations, not reusable evidence;
- avoid arbitrary Wikidata statements because this variant is ontology-focused.

The runtime marker remains:

```text
Text: ${USER_TEXT}
RDF:
```

The service also supports the legacy `${Text_TEXT}` marker. If a custom prompt contains
neither marker, the input is appended as a chat-style user turn.

## Prefixes and graph shape

The prompts authorize:

```turtle
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix wd: <http://www.wikidata.org/entity/> .
@prefix kg: <https://example.org/wikidata-description/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
```

Important graph rules include:

- exact input surface labels with language tags;
- no invented or malformed QIDs;
- `wd:` only for MCP-grounded entities/classes;
- `kg:` snake_case resources for unresolved concepts;
- `kg:is` as the preferred type/classification relation;
- direct, labeled entity-to-entity paths for evaluation-oriented answers;
- a complete period-terminated Turtle subject block.

## Prompt enforcement versus service enforcement

The prompts ask for both entity search and hierarchy inspection. The service enforces that
at least one allowlisted MCP tool is called when `REQUIRE_WIKIDATA_MCP=true`; it does not
force a specific tool sequence. Consequently, whether hierarchy lookup is appropriate for
each mention remains a model decision. The service does enforce the allowlist, so the model
cannot invoke tools such as `get_statements` or `execute_sparql` under the default profile.

## Editing guidelines

- Keep `${USER_TEXT}` unless chat-style appending is intentional.
- Keep examples syntactically valid and all used prefixes declared.
- Keep the statement that example QIDs are not evidence for a new request.
- Do not instruct the model to use tools absent from `WIKIDATA_MCP_TOOLS`.
- Keep ontology evidence separate from relations stated by the source text.
- Keep labels mandatory because downstream questions compare answer surfaces.
- Preserve Turtle-only final output; tool calls already use a separate structured channel.
- Update `tests/unit/test_prompts.py` when changing critical grounding constraints.
