from __future__ import annotations

from typing import Any

from ontology_based.infrastructure.wikidata_mcp_client import (
    WikidataMCPClient,
    WikidataMCPConfig,
)


class FakeResponse:
    def __init__(self, data: dict[str, Any], headers: dict[str, str] | None = None):
        self._data = data
        self.headers = headers or {}
        self.text = "json"
        self.encoding: str | None = None

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._data


def test_discovers_allowlisted_tools_and_calls_with_default_language(monkeypatch):
    payloads: list[dict[str, Any]] = []
    responses: list[FakeResponse] = []

    def fake_post(url, headers, json, timeout):
        payloads.append(json)
        method = json["method"]
        if method == "initialize":
            response = FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {}}, {"Mcp-Session-Id": "s1"})
        elif method == "notifications/initialized":
            response = FakeResponse({})
        elif method == "tools/list":
            response = FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "search_items",
                                "description": "Search items",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"query": {"type": "string"}, "lang": {"type": "string"}},
                                },
                            },
                            {"name": "execute_sparql", "inputSchema": {"type": "object"}},
                        ]
                    },
                }
            )
        else:
            assert method == "tools/call"
            response = FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {"content": [{"type": "text", "text": "Q7251: Alan Turing"}]},
                }
            )
        responses.append(response)
        return response

    monkeypatch.setattr("ontology_based.infrastructure.wikidata_mcp_client.requests.post", fake_post)
    client = WikidataMCPClient(WikidataMCPConfig(language="pt", allowed_tools=("search_items",)))

    tools = client.ollama_tools()
    result = client.call_tool("search_items", {"query": "Alan Turing"})

    assert [tool["function"]["name"] for tool in tools] == ["search_items"]
    assert result == "Q7251: Alan Turing"
    call_payload = next(payload for payload in payloads if payload["method"] == "tools/call")
    assert call_payload["params"]["arguments"]["lang"] == "pt"
    assert all(tool["function"]["name"] != "execute_sparql" for tool in tools)
    assert all(response.encoding == "utf-8" for response in responses)


def test_normalizes_model_generated_tool_arguments(monkeypatch):
    payloads: list[dict[str, Any]] = []

    def fake_post(url, headers, json, timeout):
        payloads.append(json)
        method = json["method"]
        if method == "initialize":
            return FakeResponse(
                {"jsonrpc": "2.0", "id": 1, "result": {}},
                {"Mcp-Session-Id": "s1"},
            )
        if method == "notifications/initialized":
            return FakeResponse({})
        if method == "tools/list":
            return FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "get_instance_and_subclass_hierarchy",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "entity_id": {"type": "string"},
                                        "max_depth": {"type": "integer"},
                                    },
                                },
                            }
                        ]
                    },
                }
            )
        assert method == "tools/call"
        return FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {"content": [{"type": "text", "text": "hierarchy"}]},
            }
        )

    monkeypatch.setattr(
        "ontology_based.infrastructure.wikidata_mcp_client.requests.post", fake_post
    )
    client = WikidataMCPClient(
        WikidataMCPConfig(allowed_tools=("get_instance_and_subclass_hierarchy",))
    )

    result = client.call_tool(
        "get_instance_and_subclass_hierarchy",
        {"qids": '["wd:Q7251"]', "max_depth": "2"},
    )

    assert result == "hierarchy"
    call_payload = next(payload for payload in payloads if payload["method"] == "tools/call")
    assert call_payload["params"]["arguments"] == {
        "entity_id": "Q7251",
        "max_depth": 2,
    }
