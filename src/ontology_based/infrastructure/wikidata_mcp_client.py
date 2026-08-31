from __future__ import annotations

import itertools
import json
import os
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class WikidataMCPConfig:
    url: str = "https://wd-mcp.wmcloud.org/mcp/"
    language: str = "en"
    timeout_seconds: float = 60.0
    user_agent: str = "ontology-based-agent/1.0"
    allowed_tools: tuple[str, ...] = (
        "search_items",
        "get_instance_and_subclass_hierarchy",
    )

    @classmethod
    def from_env(cls) -> WikidataMCPConfig:
        allowed = os.getenv(
            "WIKIDATA_MCP_TOOLS",
            "search_items,get_instance_and_subclass_hierarchy",
        )
        try:
            timeout = float(os.getenv("WIKIDATA_TIMEOUT_SECONDS", "60"))
        except ValueError:
            timeout = 60.0
        return cls(
            url=os.getenv("WIKIDATA_MCP_URL", "https://wd-mcp.wmcloud.org/mcp/"),
            language=os.getenv("WIKIDATA_LANGUAGE", "en"),
            timeout_seconds=timeout,
            user_agent=os.getenv("WIKIDATA_USER_AGENT", "ontology-based-agent/1.0"),
            allowed_tools=tuple(name.strip() for name in allowed.split(",") if name.strip()),
        )


class WikidataMCPClient:
    """Streamable-HTTP MCP client that exposes a restricted ontology tool set to Ollama."""

    def __init__(self, config: WikidataMCPConfig):
        self.config = config
        self._ids = itertools.count(1)
        self._session_id: str | None = None
        self._initialized = False
        self._tool_cache: list[dict[str, Any]] | None = None

    def health(self) -> dict[str, Any]:
        try:
            tools = self.list_tools()
            return {
                "status": "ok",
                "url": self.config.url,
                "tools": [tool["name"] for tool in tools],
            }
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            return {"status": "unavailable", "url": self.config.url, "details": str(exc)}

    def ollama_tools(self) -> list[dict[str, Any]]:
        tools = []
        for tool in self.list_tools():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description") or "Wikidata ontology lookup",
                        "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
                    },
                }
            )
        if not tools:
            raise RuntimeError("Wikidata MCP exposed none of the configured ontology tools.")
        return tools

    def list_tools(self) -> list[dict[str, Any]]:
        if self._tool_cache is not None:
            return self._tool_cache
        self._ensure_initialized()
        discovered: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            data, _ = self._post_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": next(self._ids),
                    "method": "tools/list",
                    "params": params,
                }
            )
            _raise_rpc_error(data)
            result = data.get("result") or {}
            discovered.extend(tool for tool in result.get("tools", []) if isinstance(tool, dict))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        allowed = set(self.config.allowed_tools)
        self._tool_cache = [
            tool for tool in discovered if isinstance(tool.get("name"), str) and tool["name"] in allowed
        ]
        return self._tool_cache

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        available = {tool["name"]: tool for tool in self.list_tools()}
        if name not in available:
            raise ValueError(f"MCP tool {name!r} is not allowed for ontology-based analysis.")
        schema = available[name].get("inputSchema") or {}
        properties = schema.get("properties") or {}
        arguments = _normalize_arguments(arguments, schema)
        if "lang" in properties and "lang" not in arguments:
            arguments["lang"] = self.config.language
        data, _ = self._post_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": next(self._ids),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        _raise_rpc_error(data)
        result = data.get("result") or {}
        if result.get("isError"):
            raise RuntimeError(f"Wikidata MCP tool {name!r} failed: {_tool_result_text(result)}")
        return _tool_result_text(result)

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        data, response = self._post_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": next(self._ids),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "ontology-based", "version": "1.0.0"},
                },
            },
            initializing=True,
        )
        _raise_rpc_error(data)
        self._session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
        self._initialized = True
        with suppress(requests.RequestException, RuntimeError, ValueError):
            self._post_jsonrpc({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post_jsonrpc(
        self, payload: dict[str, Any], initializing: bool = False
    ) -> tuple[dict[str, Any], requests.Response]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": self.config.user_agent,
        }
        if self._session_id and not initializing:
            headers["Mcp-Session-Id"] = self._session_id
        response = requests.post(
            self.config.url,
            headers=headers,
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        # The hosted endpoint may omit a charset for SSE. Requests then assumes
        # ISO-8859-1, corrupting Unicode labels before they reach the model.
        response.encoding = "utf-8"
        if response.text.lstrip().startswith(("data:", "event:")):
            return _parse_event_stream(response.text), response
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Wikidata MCP returned a non-object JSON-RPC response.")
        return data, response


def _raise_rpc_error(data: dict[str, Any]) -> None:
    if "error" in data:
        raise RuntimeError(f"Wikidata MCP JSON-RPC error: {data['error']}")


def _parse_event_stream(text: str) -> dict[str, Any]:
    for line in reversed(text.splitlines()):
        if line.startswith("data:"):
            payload = json.loads(line.removeprefix("data:").strip())
            if isinstance(payload, dict):
                return payload
    raise ValueError("Wikidata MCP returned an event stream without JSON data.")


def _tool_result_text(result: dict[str, Any]) -> str:
    blocks = result.get("content") or []
    text_parts = [
        block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text"
    ]
    if text_parts:
        return "\n".join(part for part in text_parts if part)
    if "structuredContent" in result:
        return json.dumps(result["structuredContent"], ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


def _normalize_arguments(
    arguments: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Normalize model-generated arguments according to the MCP input schema."""
    properties = schema.get("properties") or {}
    normalized = dict(arguments)

    if "entity_id" in properties and "entity_id" not in normalized:
        for alias in ("ids", "qids", "entity_ids", "qid", "id"):
            if alias not in normalized:
                continue
            candidate = normalized.pop(alias)
            if isinstance(candidate, str):
                with suppress(json.JSONDecodeError):
                    decoded = json.loads(candidate)
                    candidate = decoded
            if isinstance(candidate, list) and candidate:
                candidate = candidate[0]
            if isinstance(candidate, str) and candidate.strip():
                normalized["entity_id"] = candidate.strip()
            break

    for name, value in normalized.items():
        property_schema = properties.get(name)
        if not isinstance(property_schema, dict):
            continue
        if name == "entity_id" and isinstance(value, str):
            normalized[name] = value.removeprefix("wd:").strip()
        if property_schema.get("type") == "integer" and isinstance(value, str):
            # Invalid values stay untouched so the MCP server can return its
            # normal schema-validation error instead of changing semantics.
            with suppress(ValueError):
                normalized[name] = int(value.strip())
    return normalized
