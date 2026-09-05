# Prompt behavior

The ontology pipeline uses the same structured RDF triple contract as the prompt-based and hybrid
pipelines, with an additional Wikidata MCP tool phase.

## Tool phase

The model receives only the configured Wikidata tools. It resolves recognizable entities and
inspects relevant instance/subclass information. QIDs may be used only when returned during the
current request. Tool calls and results are retained in the audit response.

When the model finishes gathering evidence, the service disables tools and starts a final response
round. This prevents the 256-token tool-selection limit from truncating the graph response. The
final round uses `OLLAMA_NUM_PREDICT` and Ollama's strict JSON Schema format.

## Model response

```json
{
  "triples": [
    {
      "subject": "wd:Q7251",
      "predicate": "rdfs:label",
      "object": "Alan Turing",
      "object_type": "literal",
      "language": "en"
    },
    {
      "subject": "wd:Q7251",
      "predicate": "kg:is",
      "object": "wd:Q5",
      "object_type": "resource"
    }
  ]
}
```

Every item requires `subject`, `predicate`, `object`, and `object_type`. Literal objects may have
either `language` or `datatype`. Supported identifiers use `wd:`, `kg:`, `rdf:`, `rdfs:`, `xsd:`,
or `owl:`.

## RDF construction

The application validates the structured response, creates RDFLib terms, adds them to a graph, and
returns `graph.serialize(format="turtle")` as the `rdf` string. The model never generates prefix
declarations or Turtle punctuation.

Invalid structured responses are retried without repeating successful Wikidata calls. The final
Turtle must parse, contain triples, and include a semantic relationship in addition to labels.

## Editing guidelines

- Keep `${USER_TEXT}` in the user prompt.
- Keep the structured fields identical across all three pipelines.
- Keep current-request Wikidata grounding mandatory.
- Keep final graph generation in a tool-disabled, schema-constrained round.
