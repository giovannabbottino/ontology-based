import json
import re
from pathlib import Path

from ontology_based.domain.structured_rdf import REQUIRED_PREFIXES, model_response_to_turtle


def test_user_prompt_examples_use_grounded_wikidata_ids_and_valid_turtle():
    prompt = Path("prompt/prompts/ontology-few-shot.txt").read_text(encoding="utf-8")
    examples = [
        json.JSONDecoder().raw_decode(prompt[match.end() :])[0]
        for match in re.finditer(r"Example response:\s*", prompt)
    ]
    assert len(examples) == 3
    expected_qids = [
        {"Q8023", "Q3926"},
        {"Q21708200", "Q95726734", "Q30642"},
        {"Q7186", "Q37463", "Q1128", "Q90"},
    ]
    for example, qids in zip(examples, expected_qids, strict=True):
        assert model_response_to_turtle(json.dumps(example)) == example["rdf"].strip()
        assert set(re.findall(r"wd:(Q[1-9][0-9]*)", example["rdf"])) == qids
    assert "${USER_TEXT}" in prompt
    assert "only for QIDs returned by Wikidata MCP during the current request" in prompt
    assert "Never copy QIDs from unrelated examples" in prompt


def test_system_prompt_requires_json_rdf_grounding_and_exact_prefixes():
    prompt = Path("prompt/system/knowledge_graph.txt").read_text(encoding="utf-8")
    assert "Return exactly one JSON object with a single key `rdf`" in prompt
    assert "only when Wikidata returned that QID during the current request" in prompt
    assert "Once tools are disabled" in prompt
    assert "Return JSON only" in prompt
    for prefix, iri in REQUIRED_PREFIXES.items():
        assert f"@prefix {prefix}: <{iri}> ." in prompt
