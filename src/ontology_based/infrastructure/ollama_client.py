from __future__ import annotations

import json
import logging
from typing import Any

import requests

from ..config import OllamaClientConfig

logger = logging.getLogger(__name__)


class OllamaChatClient:
    """Ollama `/api/chat` client with tool-call support and JSONL audit logging."""

    def __init__(self, config: OllamaClientConfig):
        self.config = config
        self._logging_disabled = False

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        num_predict: int | None = None,
        response_format: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        base_url = self.config.url.rstrip("/")
        target_url = base_url if base_url.endswith("/api/chat") else f"{base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if response_format is not None:
            payload["format"] = response_format
        options = dict(self.config.options)
        if num_predict is not None:
            options["num_predict"] = max(1, int(num_predict))
        if options:
            payload["options"] = options

        response = requests.post(target_url, json=payload, timeout=self.config.timeout_seconds)
        if response.status_code == 404:
            raise RuntimeError(
                f"Ollama model '{self.config.model}' is unavailable or does not support chat. "
                f"Run: ollama pull {self.config.model}."
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
            raise RuntimeError("Invalid JSON response from Ollama chat API.")
        self._log(messages, data)
        return data

    def health_check(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.config.url.rstrip('/')}/api/tags", timeout=5)
            response.raise_for_status()
            models = response.json().get("models", [])
            names = {item.get("name") or item.get("model") for item in models if isinstance(item, dict)}
            if self.config.model not in names:
                return {
                    "status": "missing_model",
                    "model": self.config.model,
                    "details": f"Run: ollama pull {self.config.model}",
                }
            return {"status": "ok", "model": self.config.model}
        except requests.RequestException as exc:
            return {"status": "unavailable", "details": str(exc)}

    def _log(self, messages: list[dict[str, Any]], response: dict[str, Any]) -> None:
        if self._logging_disabled:
            return
        try:
            self.config.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            message = response.get("message") or {}
            entry = {
                "model": response.get("model", self.config.model),
                "messages": messages,
                "response": message.get("content"),
                "tool_calls": message.get("tool_calls"),
                "created_at": response.get("created_at"),
            }
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with self.config.jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(line)
        except (OSError, TypeError, ValueError) as exc:
            self._logging_disabled = True
            logger.warning("Disabling Ollama JSONL logging after write failure: %s", exc)
