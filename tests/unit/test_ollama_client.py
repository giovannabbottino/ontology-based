import json
from pathlib import Path

from ontology_based.config import OllamaClientConfig
from ontology_based.domain.structured_rdf import RDF_RESPONSE_SCHEMA
from ontology_based.infrastructure.ollama_client import OllamaChatClient


class StubResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"model": "test", "message": {"role": "assistant", "content": "{}"}}


def test_chat_sends_structured_response_format(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(json)
        return StubResponse()

    monkeypatch.setattr("ontology_based.infrastructure.ollama_client.requests.post", fake_post)
    client = OllamaChatClient(
        OllamaClientConfig(url="http://ollama:11434", jsonl_path=tmp_path / "responses.jsonl")
    )

    client.chat(
        [{"role": "user", "content": "build graph"}],
        response_format=RDF_RESPONSE_SCHEMA,
    )

    assert captured["format"]["required"] == ["rdf"]
    assert captured["format"]["additionalProperties"] is False

    assert captured["format"]["properties"]["rdf"]["type"] == "string"


def test_chat_appends_jsonl_with_nested_messages_and_tool_calls(monkeypatch, tmp_path):
    messages = [{"role": "user", "content": "S\u00e3o Paulo\nBrazil"}]
    tool_calls = [{"function": {"name": "search_items", "arguments": {"query": "S\u00e3o Paulo"}}}]
    response_data = {
        "model": "test-model",
        "created_at": "2026-11-09T12:00:00Z",
        "message": {"content": "Line one\nLine two", "tool_calls": tool_calls},
    }
    monkeypatch.setattr(StubResponse, "json", lambda self: response_data)
    monkeypatch.setattr(
        "ontology_based.infrastructure.ollama_client.requests.post", lambda *a, **kw: StubResponse()
    )
    path = tmp_path / "logs" / "responses.jsonl"
    client = OllamaChatClient(OllamaClientConfig(jsonl_path=path))
    client.chat(messages)
    client.chat(messages)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line) for line in lines] == [
        {
            "model": "test-model",
            "messages": messages,
            "response": "Line one\nLine two",
            "tool_calls": tool_calls,
            "created_at": "2026-11-09T12:00:00Z",
        }
    ] * 2


def test_chat_succeeds_when_jsonl_cannot_be_written(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "ontology_based.infrastructure.ollama_client.requests.post", lambda *a, **kw: StubResponse()
    )
    blocked = tmp_path / "blocked"
    blocked.write_text("file instead of directory", encoding="utf-8")
    client = OllamaChatClient(OllamaClientConfig(jsonl_path=blocked / "responses.jsonl"))
    assert client.chat([{"role": "user", "content": "Example"}])["message"]["content"] == "{}"
    assert client._logging_disabled
