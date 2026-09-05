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
                    "content": _structured_paris(),
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": _structured_paris(),
                }
            },
        ]

    def chat(self, messages, tools=None, num_predict=None, response_format=None):
        return self.responses.pop(0)

    def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "model": "test"}


def _structured_paris() -> str:
    return json.dumps(
        {
            "triples": [
                {
                    "subject": "wd:Q90",
                    "predicate": "rdfs:label",
                    "object": "Paris",
                    "object_type": "literal",
                    "language": "en",
                },
                {
                    "subject": "kg:city",
                    "predicate": "rdfs:label",
                    "object": "city",
                    "object_type": "literal",
                    "language": "en",
                },
                {
                    "subject": "wd:Q90",
                    "predicate": "kg:is",
                    "object": "kg:city",
                    "object_type": "resource",
                },
            ]
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
