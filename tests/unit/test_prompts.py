import json
from pathlib import Path

from ontology_based.domain.structured_rdf import REQUIRED_PREFIXES, model_response_to_turtle


def test_user_prompt_contains_valid_json_rdf_example_and_input_placeholder():
    prompt = Path("prompt/prompts/ontology-few-shot.txt").read_text(encoding="utf-8")
    example = json.loads(prompt.splitlines()[1])
    assert model_response_to_turtle(json.dumps(example)) == example["rdf"]
    assert "${USER_TEXT}" in prompt
    assert "current request" in prompt


def test_system_prompt_requires_json_rdf_grounding_and_exact_prefixes():
    prompt = Path("prompt/system/knowledge_graph.txt").read_text(encoding="utf-8")
    assert "Return exactly one JSON object with a single key `rdf`" in prompt
    assert "only when Wikidata returned that QID during the current request" in prompt
    assert "Once tools are disabled" in prompt
    assert "Return JSON only" in prompt
    for prefix, iri in REQUIRED_PREFIXES.items():
        assert f"@prefix {prefix}: <{iri}> ." in prompt
