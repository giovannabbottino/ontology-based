from __future__ import annotations

import csv
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _int_env(name: str) -> int | None:
    value = os.getenv(name)
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _float_env(name: str) -> float | None:
    value = os.getenv(name)
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


@dataclass(frozen=True)
class OllamaOptions:
    values: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> OllamaOptions:
        values: dict[str, Any] = {}
        for key, env_name, reader in (
            ("seed", "OLLAMA_SEED", _int_env),
            ("temperature", "OLLAMA_TEMPERATURE", _float_env),
            ("top_k", "OLLAMA_TOP_K", _int_env),
            ("top_p", "OLLAMA_TOP_P", _float_env),
            ("min_p", "OLLAMA_MIN_P", _float_env),
            ("num_ctx", "OLLAMA_NUM_CTX", _int_env),
            ("num_predict", "OLLAMA_NUM_PREDICT", _int_env),
        ):
            value = reader(env_name)
            if value is not None:
                values[key] = value
        stop = os.getenv("OLLAMA_STOP")
        if stop:
            values["stop"] = stop
        return cls(values)


@dataclass(frozen=True)
class OllamaClientConfig:
    url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    csv_path: Path = Path("data/ollama_responses.csv")
    timeout_seconds: float = 300.0
    options: OllamaOptions = field(default_factory=OllamaOptions)

    @classmethod
    def from_env(cls) -> OllamaClientConfig:
        return cls(
            url=os.getenv("OLLAMA_API_URL", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
            csv_path=Path(os.getenv("OLLAMA_CSV_PATH", "data/ollama_responses.csv")),
            timeout_seconds=_float_env("OLLAMA_TIMEOUT_SECONDS") or 300.0,
            options=OllamaOptions.from_env(),
        )


class OllamaChatClient:
    """Ollama `/api/chat` client with tool-call support and CSV audit logging."""

    def __init__(self, config: OllamaClientConfig):
        self.config = config
        self._logging_disabled = False

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        num_predict: int | None = None,
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
        options = dict(self.config.options.values)
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
            self.config.csv_path.parent.mkdir(parents=True, exist_ok=True)
            write_header = not self.config.csv_path.exists()
            with self.config.csv_path.open("a", encoding="utf-8", newline="") as stream:
                fieldnames = ["model", "messages", "response", "tool_calls", "created_at"]
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()
                message = response.get("message") or {}
                writer.writerow(
                    {
                        "model": response.get("model", self.config.model),
                        "messages": json.dumps(messages, ensure_ascii=False),
                        "response": message.get("content"),
                        "tool_calls": json.dumps(message.get("tool_calls"), ensure_ascii=False),
                        "created_at": response.get("created_at"),
                    }
                )
        except OSError as exc:
            self._logging_disabled = True
            logger.warning("Disabling Ollama CSV logging after write failure: %s", exc)
