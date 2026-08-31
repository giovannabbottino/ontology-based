# Prompt documentation

The ontology-based service uses this pair:

- `prompt/system/knowledge_graph.txt`
- `prompt/prompts/ontology-few-shot.txt`

Its core instructions, prefixes, input markers, and two few-shot examples are identical to `prompt-based`. The only intentional difference is a dedicated Wikidata-grounding block in the ontology user and system prompts.

## Shared system prompt

The shared system prompt assigns the role `RDF knowledge graph engineer` and requires:

- RDF/Turtle-only output;
- strict RDF 1.1 Turtle syntax;
- `;` between different predicates for the same subject;
- `,` only between multiple objects of the same predicate;
- `.` at the end of every statement;
- an object for every predicate;
- every used prefix declared in the same response before its first use;
- the exact `kg:` declaration whenever a `kg:` name is used;
- no adjacent objects without Turtle punctuation;
- `rdfs:label` with a language tag for every resource;
- no invented Wikidata QIDs.

The complete result must parse with `rdflib.Graph.parse(format="turtle")`, and valid Turtle syntax takes precedence over every other instruction or example.

## Shared few-shot prompt

The generic user prompt represents the entities, concepts, and relationships stated in the input without imposing a domain-specific ontology or a long fixed predicate vocabulary. It declares `rdfs:`, `wd:`, `kg:`, and `xsd:`.

Both projects use the same two examples:

1. a person managing a research laboratory located in Lisbon;
2. a mango classified as a fruit.

The examples use local `kg:` resources and demonstrate labeled, connected graphs, Turtle predicate separators, statement termination, and `kg:is` classification. Unit tests extract and parse both example documents with RDFLib.

## Ontology-only Wikidata grounding

The ontology prompt adds these requirements without changing the shared examples:

- use the available Wikidata tools before producing the final RDF;
- resolve recognizable entities from `<CURRENT_TEXT>`;
- inspect relevant instance/subclass information;
- use only QIDs returned by Wikidata during the current request;
- never call Wikidata tools for entities shown only in `<EXAMPLES>`;
- use Wikidata for entity and classification grounding while keeping other relationships limited to what the source text states.

The service exposes only the tools configured by `WIKIDATA_MCP_TOOLS`. With `REQUIRE_WIKIDATA_MCP=true`, at least one allowlisted tool call is required, but the service does not force a fixed tool sequence.

Tool calls are structured Ollama messages and do not appear in the final Turtle response.

## Current input marker

The examples and request are separated explicitly:

```text
<EXAMPLES>
...
</EXAMPLES>

<CURRENT_TEXT>
Text:
${USER_TEXT}
</CURRENT_TEXT>

RDF/Turtle:
```

The legacy `${Text_TEXT}` marker remains supported for custom prompts. If neither marker exists, the service appends the input as a user turn.

## Runtime validation and retry

The final response is parsed strictly with RDFLib. If parsing fails, the same LLM conversation receives the parser error and is asked to regenerate the complete Turtle document. Successful Wikidata calls are retained and are not repeated solely because RDF syntax was invalid. No local syntax repair or substitute graph is used.

## Editing guidelines

- Keep the prompt core and examples identical to `prompt-based`.
- Put Wikidata-specific instructions only in the dedicated grounding blocks.
- Keep `${USER_TEXT}` inside `<CURRENT_TEXT>` and exclude `<EXAMPLES>` from tool scope.
- Keep every example self-contained and valid according to RDFLib.
- Keep the shared mandatory syntax block identical in all three pipelines.
- Keep prefix binding and the distinction between `;`, `,`, and `.` explicit.
- Do not instruct the model to use tools absent from `WIKIDATA_MCP_TOOLS`.
- Keep Wikidata grounding separate from relationships stated by the source text.
- Update `tests/unit/test_prompts.py` whenever the shared contract or grounding rules change.
