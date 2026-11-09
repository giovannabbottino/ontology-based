from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _int_env(name: str) -> int | None:
    value = os.getenv(name)
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _positive_int_env(name: str, default: int) -> int:
    value = _int_env(name)
    return max(1, default if value is None else value)


def _float_env(name: str) -> float | None:
    value = os.getenv(name)
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


@dataclass(frozen=True)
class OllamaClientConfig:
    url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    jsonl_path: Path = Path("logs/ollama_responses.jsonl")
    timeout_seconds: float = 300.0
    options: dict[str, Any] = field(
        default_factory=lambda: {
            "seed": 42,
            "temperature": 0.0,
            "top_k": 1,
            "top_p": 1.0,
            "min_p": 0.0,
            "num_predict": 2048,
        }
    )


@dataclass(frozen=True)
class WikidataMCPConfig:
    url: str = "https://wd-mcp.wmcloud.org/mcp/"
    language: str = "en"
    timeout_seconds: float = 60.0
    user_agent: str = "ontology-based-agent/1.0"
    allowed_tools: tuple[str, ...] = ("search_items", "get_instance_and_subclass_hierarchy")


@dataclass(frozen=True)
class AppConfig:
    default_prompt: str = "prompts/ontology-few-shot.txt"
    default_system_prompt: str = "system/knowledge_graph.txt"
    analyze_log_path: str = "logs/analyze_log.jsonl"
    max_tool_rounds: int = 8
    max_tool_calls: int = 4
    max_tool_result_chars: int = 1500
    tool_num_predict: int = 256
    require_mcp: bool = True
    ollama: OllamaClientConfig = field(default_factory=OllamaClientConfig)
    wikidata: WikidataMCPConfig = field(default_factory=WikidataMCPConfig)

    @classmethod
    def from_env(cls) -> AppConfig:
        defaults = cls()
        require_mcp = os.getenv("REQUIRE_WIKIDATA_MCP", "true")
        allowed = os.getenv("WIKIDATA_MCP_TOOLS", ",".join(defaults.wikidata.allowed_tools))
        return cls(
            default_prompt=os.getenv("DEFAULT_PROMPT_NAME", defaults.default_prompt),
            default_system_prompt=os.getenv("DEFAULT_SYSTEM_PROMPT_NAME", defaults.default_system_prompt),
            analyze_log_path=os.getenv("ANALYZE_LOG_PATH", defaults.analyze_log_path),
            max_tool_rounds=_positive_int_env("MAX_TOOL_ROUNDS", defaults.max_tool_rounds),
            max_tool_calls=_positive_int_env("MAX_TOOL_CALLS", defaults.max_tool_calls),
            max_tool_result_chars=_positive_int_env("MAX_TOOL_RESULT_CHARS", defaults.max_tool_result_chars),
            tool_num_predict=_positive_int_env("OLLAMA_TOOL_NUM_PREDICT", defaults.tool_num_predict),
            require_mcp=require_mcp.strip().casefold() in {"", "1", "true", "yes", "on"},
            ollama=OllamaClientConfig(
                url=os.getenv("OLLAMA_API_URL", defaults.ollama.url),
                model=os.getenv("OLLAMA_MODEL", defaults.ollama.model),
                jsonl_path=Path(os.getenv("OLLAMA_JSONL_PATH", str(defaults.ollama.jsonl_path))),
                timeout_seconds=_float_env("OLLAMA_TIMEOUT_SECONDS") or defaults.ollama.timeout_seconds,
                options=cls._ollama_options(),
            ),
            wikidata=WikidataMCPConfig(
                url=os.getenv("WIKIDATA_MCP_URL", defaults.wikidata.url),
                language=os.getenv("WIKIDATA_LANGUAGE", defaults.wikidata.language),
                timeout_seconds=_float_env("WIKIDATA_TIMEOUT_SECONDS") or defaults.wikidata.timeout_seconds,
                user_agent=os.getenv("WIKIDATA_USER_AGENT", defaults.wikidata.user_agent),
                allowed_tools=tuple(name.strip() for name in allowed.split(",") if name.strip()),
            ),
        )

    @staticmethod
    def _ollama_options() -> dict[str, Any]:
        values = dict(OllamaClientConfig().options)
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
        return values
