from pathlib import Path


def test_user_prompt_is_generic_with_wikidata_grounding():
    prompt = Path("prompt/prompts/ontology-few-shot.txt").read_text(encoding="utf-8")

    assert "Convert the text below into a knowledge graph" in prompt
    assert "Follow RDF 1.1 Turtle syntax strictly" in prompt
    assert "different predicates for the same subject with `;`" in prompt
    assert "multiple objects of the same predicate with `,`" in prompt
    assert 'rdflib.Graph.parse(format="turtle")' in prompt
    assert "available Wikidata tools" in prompt
    assert "instance/subclass information" in prompt
    assert "only QIDs returned by Wikidata" in prompt
    assert "${USER_TEXT}" in prompt
    assert "<EXAMPLES>" not in prompt


def test_system_prompt_assigns_role_and_requires_wikidata_and_strict_turtle():
    prompt = Path("prompt/system/knowledge_graph.txt").read_text(encoding="utf-8")

    assert prompt.startswith("Role: You are an RDF knowledge graph engineer.")
    assert "Follow RDF 1.1 Turtle syntax strictly" in prompt
    assert "Use `;` between different predicates" in prompt
    assert "Use `,` only between multiple objects" in prompt
    assert "available Wikidata tools before answering" in prompt
    assert "Use a `wd:Q...` resource only when Wikidata returned" in prompt
    assert "Valid Turtle syntax takes precedence" in prompt
