from __future__ import annotations

import json
from typing import Any

import pytest

from ontology_based.application.services import OntologyKnowledgeGraphService, RDFValidationError
from ontology_based.domain.models import AnalyzeRequest
from ontology_based.infrastructure.request_logger import RequestLogger


class StubPromptRepository:
    def load_prompt(self, prompt_name: str) -> str:
        if prompt_name.startswith("system/"):
            return "Use Wikidata MCP, then return structured RDF JSON."
        return "Build structured RDF JSON for: ${USER_TEXT}"


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
        self.tool_requests: list[list[dict[str, Any]] | None] = []
        self.num_predict_requests: list[int | None] = []
        self.response_formats: list[dict[str, Any] | str | None] = []

    def chat(self, messages, tools=None, num_predict=None, response_format=None):
        self.requests.append(list(messages))
        self.tool_requests.append(tools)
        self.num_predict_requests.append(num_predict)
        self.response_formats.append(response_format)
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
    return json.dumps(
        {
            "triples": [
                {
                    "subject": "wd:Q7251",
                    "predicate": "rdfs:label",
                    "object": "Alan Turing",
                    "object_type": "literal",
                    "language": "en",
                },
                {
                    "subject": "wd:Q5",
                    "predicate": "rdfs:label",
                    "object": "human",
                    "object_type": "literal",
                    "language": "en",
                },
                {
                    "subject": "wd:Q7251",
                    "predicate": "kg:is",
                    "object": "wd:Q5",
                    "object_type": "resource",
                },
            ]
        }
    )


def test_analyze_uses_search_and_hierarchy_before_returning_rdf():
    wikidata = StubWikidata()
    llm = StubLLM(
        [
            tool_call("search_items", {"query": "Alan Turing"}),
            tool_call("get_instance_and_subclass_hierarchy", {"entity_id": "Q7251"}),
            {"role": "assistant", "content": valid_rdf()},
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
    assert llm.requests[0][1]["content"] == ("Build structured RDF JSON for: Alan Turing was a human.")
    assert llm.requests[1][-1]["role"] == "tool"
    assert llm.tool_requests[-1] is None
    assert llm.response_formats[-1] is not None


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
    assert llm.tool_requests[-1] is None
    assert "previous structured RDF JSON" in llm.requests[-1][-1]["content"]
    assert "Previous invalid response:\nnot rdf" in llm.requests[-1][-1]["content"]


def test_invalid_rdf_is_rejected_without_local_repair():
    invalid_rdf = (
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix wd: <http://www.wikidata.org/entity/> .\n"
        'wd:Q7251 rdfs:label ""Alan Turing"" .'
    )
    llm = StubLLM(
        [
            tool_call("search_items", {"query": "Alan Turing"}),
            {"role": "assistant", "content": invalid_rdf},
            {"role": "assistant", "content": invalid_rdf},
        ]
    )
    service = OntologyKnowledgeGraphService(
        StubPromptRepository(),
        default_prompt="prompts/ontology-few-shot.txt",
        default_system_prompt="system/knowledge_graph.txt",
        llm=llm,
        wikidata=StubWikidata(),
    )

    with pytest.raises(RDFValidationError):
        service.analyze(AnalyzeRequest(text="Alan Turing was a human.", max_rdf_attempts=1))


def test_limits_tool_calls_and_result_context():
    wikidata = StubWikidata()
    requested_calls = [
        {
            "function": {
                "name": "search_items",
                "arguments": {"query": f"entity {index}"},
            }
        }
        for index in range(6)
    ]
    llm = StubLLM(
        [
            {"role": "assistant", "content": "", "tool_calls": requested_calls},
            {"role": "assistant", "content": valid_rdf()},
        ]
    )
    service = OntologyKnowledgeGraphService(
        StubPromptRepository(),
        default_prompt="prompts/ontology-few-shot.txt",
        default_system_prompt="system/knowledge_graph.txt",
        llm=llm,
        wikidata=wikidata,
        max_tool_calls=2,
        max_tool_result_chars=20,
    )

    response = service.analyze(AnalyzeRequest(text="Alan Turing was a human."))

    assert len(response.mcp_calls) == 2
    assert len(wikidata.calls) == 2
    assert llm.tool_requests[0]
    assert llm.tool_requests[1] is None
    assert llm.num_predict_requests == [256, None]
    assert llm.response_formats[0] is None
    assert llm.response_formats[1] is not None
    tool_messages = [message for message in llm.requests[1] if message["role"] == "tool"]
    assert all(len(message["content"]) <= 23 for message in tool_messages)
    assert "tool-call budget is exhausted" in llm.requests[1][-1]["content"]


def test_analyze_logs_request_lifecycle_with_idempotence_key(tmp_path):
    log_path = tmp_path / "analyze.jsonl"
    service = OntologyKnowledgeGraphService(
        StubPromptRepository(),
        default_prompt="prompts/ontology-few-shot.txt",
        default_system_prompt="system/knowledge_graph.txt",
        llm=StubLLM([{"role": "assistant", "content": valid_rdf()}]),
        wikidata=StubWikidata(),
        require_mcp=False,
        request_logger=RequestLogger(log_path),
    )

    service.analyze(AnalyzeRequest(text="Alan Turing was a human.", idempotence_key="request-123"))

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert {entry["idempotence_key"] for entry in entries} == {"request-123"}
    assert [entry["event"] for entry in entries] == [
        "analyze_started",
        "llm_chat_request",
        "llm_chat_response",
        "rdf_validated",
        "analyze_completed",
    ]
