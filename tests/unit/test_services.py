from __future__ import annotations

from typing import Any

import pytest

from ontology_based.application.services import OntologyKnowledgeGraphService
from ontology_based.domain.models import AnalyzeRequest


class StubPromptRepository:
    def load_prompt(self, prompt_name: str) -> str:
        if prompt_name.startswith("system/"):
            return "Use Wikidata MCP, then return Turtle."
        return "Build RDF for: ${USER_TEXT}"


class StubWikidata:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def ollama_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_items",
                    "description": "search",
                    "parameters": {"type": "object"},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_instance_and_subclass_hierarchy",
                    "description": "hierarchy",
                    "parameters": {"type": "object"},
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        if name == "search_items":
            return '[{"id":"Q7251","label":"Alan Turing"}]'
        return '{"Q7251":{"instance_of":[{"id":"Q5","label":"human"}]}}'

    def health(self) -> dict[str, Any]:
        return {"status": "ok"}


class StubLLM:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.responses = list(messages)
        self.requests: list[list[dict[str, Any]]] = []

    def chat(self, messages, tools=None):
        self.requests.append(list(messages))
        return {"message": self.responses.pop(0)}

    def health_check(self) -> dict[str, Any]:
        return {"status": "ok"}


def tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


def valid_rdf() -> str:
    return (
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix wd: <http://www.wikidata.org/entity/> .\n"
        "@prefix kg: <https://example.org/wikidata-description/> .\n"
        'wd:Q7251 rdfs:label "Alan Turing"@en ; kg:is wd:Q5 .\n'
        'wd:Q5 rdfs:label "human"@en .'
    )


def test_analyze_uses_search_and_hierarchy_before_returning_rdf():
    wikidata = StubWikidata()
    llm = StubLLM(
        [
            tool_call("search_items", {"query": "Alan Turing"}),
            tool_call("get_instance_and_subclass_hierarchy", {"entity_id": "Q7251"}),
            {"role": "assistant", "content": valid_rdf()},
        ]
    )
    service = OntologyKnowledgeGraphService(
        StubPromptRepository(),
        default_prompt="prompts/ontology-few-shot.txt",
        default_system_prompt="system/knowledge_graph.txt",
        llm=llm,
        wikidata=wikidata,
    )

    response = service.analyze(AnalyzeRequest(text="Alan Turing was a human."))

    assert "wd:Q7251" in response.rdf
    assert [call[0] for call in wikidata.calls] == [
        "search_items",
        "get_instance_and_subclass_hierarchy",
    ]
    assert [call["name"] for call in response.mcp_calls] == [
        "search_items",
        "get_instance_and_subclass_hierarchy",
    ]
    assert llm.requests[0][1]["content"] == "Build RDF for: Alan Turing was a human."
    assert llm.requests[1][-1]["role"] == "tool"


def test_analyze_rejects_prompt_only_answer_when_mcp_is_required():
    llm = StubLLM(
        [
            {"role": "assistant", "content": valid_rdf()},
            {"role": "assistant", "content": valid_rdf()},
        ]
    )
    service = OntologyKnowledgeGraphService(
        StubPromptRepository(),
        default_prompt="prompts/ontology-few-shot.txt",
        default_system_prompt="system/knowledge_graph.txt",
        llm=llm,
        wikidata=StubWikidata(),
    )

    with pytest.raises(RuntimeError, match="did not call"):
        service.analyze(AnalyzeRequest(text="Alan Turing was a human."))

    assert "Use the available Wikidata tools" in llm.requests[1][-1]["content"]


def test_invalid_rdf_is_retried_without_requiring_duplicate_mcp_calls():
    wikidata = StubWikidata()
    llm = StubLLM(
        [
            tool_call("search_items", {"query": "Alan Turing"}),
            {"role": "assistant", "content": "not rdf"},
            {"role": "assistant", "content": valid_rdf()},
        ]
    )
    service = OntologyKnowledgeGraphService(
        StubPromptRepository(),
        default_prompt="prompts/ontology-few-shot.txt",
        default_system_prompt="system/knowledge_graph.txt",
        llm=llm,
        wikidata=wikidata,
    )

    response = service.analyze(AnalyzeRequest(text="Alan Turing was a human.", max_rdf_attempts=2))

    assert "wd:Q7251" in response.rdf
    assert len(response.mcp_calls) == 1
    assert "previous answer was not valid Turtle RDF" in llm.requests[-1][-1]["content"]
