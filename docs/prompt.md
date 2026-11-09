# Prompts

`prompt/system/knowledge_graph.txt` defines the rules; `prompt/prompts/ontology-few-shot.txt` contains examples with Wikidata QIDs and the `${USER_TEXT}` placeholder. Configure their paths in `.env`.
During the MCP phase, the model looks up entities and hierarchies from the input text. During final generation, tools are disabled and the schema requires a single `rdf` key of type string. QIDs must come from the current request's lookups; unresolved entities use `kg:snake_case` names.
The Turtle string must begin with these declarations:

```turtle
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix wd: <http://www.wikidata.org/entity/> .
@prefix kg: <https://example.org/wikidata-description/> .
```

Example LLM output:

```json
{"rdf": "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix wd: <http://www.wikidata.org/entity/> .\n@prefix kg: <https://example.org/wikidata-description/> .\nwd:Q7251 rdfs:label \"Alan Turing\"@en ; kg:is wd:Q5 .\nwd:Q5 rdfs:label \"human\"@en ."}
```

Turtle newlines and quotes must be escaped inside the JSON string. Empty or invalid responses are sent back to the model with the validation error, up to three attempts in total. MCP lookups are not repeated during these attempts.
