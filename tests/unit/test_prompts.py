from pathlib import Path


def test_user_prompt_requires_structured_rdf_json_and_wikidata_grounding():
    prompt = Path("prompt/prompts/ontology-few-shot.txt").read_text(encoding="utf-8")

    assert "structured" in prompt
    assert "RDF triples" in prompt
    assert '"triples"' in prompt
    assert '"subject"' in prompt
    assert '"predicate"' in prompt
    assert '"object_type"' in prompt
    assert "Return JSON only" in prompt
    assert "available Wikidata tools" in prompt
    assert "Use only QIDs returned by Wikidata" in prompt
    assert "${USER_TEXT}" in prompt


def test_system_prompt_assigns_role_and_delegates_turtle_serialization():
    prompt = Path("prompt/system/knowledge_graph.txt").read_text(encoding="utf-8")

    assert prompt.startswith("Role: You are a Wikidata-grounded knowledge graph extraction engineer.")
    assert "Return exactly one JSON object" in prompt
    assert "converts these" in prompt
    assert "triples to RDF/Turtle with rdflib" in prompt
    assert "Use the available Wikidata tools before answering" in prompt
    assert "object_type" in prompt
