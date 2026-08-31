from pathlib import Path

from rdflib import Graph


def _example_rdf_documents(prompt: str) -> list[str]:
    examples = prompt.split("<EXAMPLES>", 1)[1].split("</EXAMPLES>", 1)[0]
    documents = []
    for section in examples.split("RDF/Turtle:\n")[1:]:
        documents.append(section.split("\n\nText:\n", 1)[0].strip())
    return documents


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
    assert "Do not call Wikidata tools for entities shown only in `<EXAMPLES>`" in prompt
    assert "${USER_TEXT}" in prompt
    assert "<EXAMPLES>" in prompt
    assert "Alice manages a research laboratory in Lisbon." in prompt
    assert "A mango is a fruit." in prompt
    assert "<CURRENT_TEXT>" in prompt


def test_few_shot_examples_are_valid_turtle():
    prompt = Path("prompt/prompts/ontology-few-shot.txt").read_text(encoding="utf-8")
    documents = _example_rdf_documents(prompt)

    assert len(documents) == 2
    assert all(len(Graph().parse(data=document, format="turtle")) > 0 for document in documents)


def test_system_prompt_assigns_role_and_requires_wikidata_and_strict_turtle():
    prompt = Path("prompt/system/knowledge_graph.txt").read_text(encoding="utf-8")

    assert prompt.startswith("Role: You are an RDF knowledge graph engineer.")
    assert "Follow RDF 1.1 Turtle syntax strictly" in prompt
    assert "Use `;` between different predicates" in prompt
    assert "Use `,` only between multiple objects" in prompt
    assert "available Wikidata tools before answering" in prompt
    assert "Use a `wd:Q...` resource only when Wikidata returned" in prompt
    assert "Valid Turtle syntax takes precedence" in prompt
