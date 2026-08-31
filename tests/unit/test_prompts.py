from pathlib import Path


def test_prompts_require_wikidata_mcp_and_restrict_qids():
    system = Path("prompt/system/knowledge_graph.txt").read_text(encoding="utf-8")
    prompt = Path("prompt/prompts/ontology-few-shot.txt").read_text(encoding="utf-8")

    assert "search_items" in system
    assert "get_instance_and_subclass_hierarchy" in system
    assert "only authority for QIDs" in system
    assert "Only QIDs returned by MCP" in prompt
    assert "This ablation does not retrieve arbitrary Wikidata statements" in prompt
    assert "Never call tools for entities shown inside `<EXAMPLES>`" in prompt
    assert "standard RDF/Turtle grammar" in system
    assert "standard RDF/Turtle grammar" in prompt
    assert "valid Turtle syntax takes precedence" in system
    assert "valid Turtle syntax takes precedence" in prompt
    assert "<CURRENT_TEXT>" in prompt
    assert "${USER_TEXT}" in prompt
