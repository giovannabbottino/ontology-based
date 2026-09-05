from pathlib import Path

from ontology_based.domain.structured_rdf import RDF_TRIPLES_SCHEMA
from ontology_based.infrastructure.ollama_client import OllamaChatClient, OllamaClientConfig


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
        OllamaClientConfig(url="http://ollama:11434", csv_path=tmp_path / "responses.csv")
    )

    client.chat(
        [{"role": "user", "content": "build graph"}],
        response_format=RDF_TRIPLES_SCHEMA,
    )

    assert captured["format"]["required"] == ["triples"]
    assert captured["format"]["additionalProperties"] is False
