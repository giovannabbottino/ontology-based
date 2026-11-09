from __future__ import annotations

import json
from typing import Any

import pytest

from ontology_based.app import create_app


class FakeLLM:
    def __init__(self) -> None:
        self.responses = [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_items",
                                "arguments": {"query": "Paris"},
                            }
                        }
                    ],
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": _rdf_paris(),
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": _rdf_paris(),
                }
            },
        ]

    def chat(self, messages, tools=None, num_predict=None, response_format=None):
        return self.responses.pop(0)

    def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "model": "test"}


def _rdf_paris() -> str:
    return json.dumps(
        {
            "rdf": (
                "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
                "@prefix wd: <http://www.wikidata.org/entity/> .\n"
                "@prefix kg: <https://example.org/wikidata-description/> .\n"
                'wd:Q90 rdfs:label "Paris"@en ; kg:is kg:city .\n'
                'kg:city rdfs:label "city"@en .'
            )
        }
    )


class FakeWikidata:
    def ollama_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_items",
                    "description": "Search Wikidata",
                    "parameters": {"type": "object"},
                },
            }
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return '[{"id":"Q90","label":"Paris","description":"capital of France"}]'

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "tools": ["search_items"]}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ontology_based.app.OllamaChatClient", lambda config: FakeLLM())
    monkeypatch.setattr("ontology_based.app.WikidataMCPClient", lambda config: FakeWikidata())
    monkeypatch.setenv("ANALYZE_LOG_PATH", "")
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as flask_client:
        yield flask_client


def test_analyze_returns_rdf_and_mcp_audit(client):
    response = client.post("/analyze", json={"text": "Paris is a city."})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["text"] == "Paris is a city."
    assert "wd:Q90" in payload["rdf"]
    assert payload["source_attribution"] == "Source: Wikidata MCP"
    assert payload["mcp_calls"][0]["name"] == "search_items"


def test_health_checks_both_dependencies(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json()["wikidata_mcp"]["status"] == "ok"


def test_analyze_correlates_events_using_request_id(client, monkeypatch):
    from ontology_based.infrastructure.request_logger import RequestLogger

    events = []
    monkeypatch.setattr(
        RequestLogger, "log", lambda self, request_id, event, payload: events.append(request_id)
    )
    response = client.post("/analyze", json={"text": "Paris is a city.", "request_id": "request-123"})
    assert response.status_code == 200
    assert events and set(events) == {"request-123"}


def test_analyze_rejects_non_string_request_id(client):
    response = client.post("/analyze", json={"text": "Paris is a city.", "request_id": 123})
    assert response.status_code == 400


def test_analyze_returns_422_after_three_empty_rdf_attempts(monkeypatch):
    from ontology_based.application.services import OntologyKnowledgeGraphService

    # Exercise the real service behind the HTTP error mapping with no external calls.
    from ontology_based.infrastructure.prompt_repository import PromptRepository

    class EmptyLLM(FakeLLM):
        def chat(self, messages, tools=None, num_predict=None, response_format=None):
            return {"message": {"content": '{"rdf": ""}'}}

    service = OntologyKnowledgeGraphService(
        PromptRepository(),
        "prompts/ontology-few-shot.txt",
        "system/knowledge_graph.txt",
        EmptyLLM(),
        FakeWikidata(),
        require_mcp=False,
    )
    monkeypatch.setattr("ontology_based.app.OntologyKnowledgeGraphService", lambda **kwargs: service)
    app = create_app()
    response = app.test_client().post("/analyze", json={"text": "Paris is a city."})
    assert response.status_code == 422
    assert response.get_json()["attempts"] == 3
