from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import uuid4

from ..domain.models import AnalyzeRequest, AnalyzeResponse
from ..domain.structured_rdf import RDF_RESPONSE_SCHEMA, model_response_to_turtle
from ..infrastructure.request_logger import RequestLogger


class PromptLoader(Protocol):
    def load_prompt(self, prompt_name: str) -> str: ...


class ChatClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        num_predict: int | None = None,
        response_format: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]: ...

    def health_check(self) -> dict[str, Any]: ...


class OntologyClient(Protocol):
    def ollama_tools(self) -> list[dict[str, Any]]: ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str: ...

    def health(self) -> dict[str, Any]: ...


class RDFValidationError(RuntimeError):
    def __init__(self, message: str, attempts: int, last_error: str | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


class OntologyKnowledgeGraphService:
    def __init__(
        self,
        prompt_repository: PromptLoader,
        default_prompt: str,
        default_system_prompt: str,
        llm: ChatClient,
        wikidata: OntologyClient,
        max_tool_rounds: int = 8,
        max_tool_calls: int = 4,
        max_tool_result_chars: int = 1500,
        tool_num_predict: int = 256,
        require_mcp: bool = True,
        request_logger: RequestLogger | None = None,
    ) -> None:
        self.prompt_repository = prompt_repository
        self.default_prompt = default_prompt
        self.default_system_prompt = default_system_prompt
        self.llm = llm
        self.wikidata = wikidata
        self.max_tool_rounds = max(1, int(max_tool_rounds))
        self.max_tool_calls = max(1, int(max_tool_calls))
        self.max_tool_result_chars = max(1, int(max_tool_result_chars))
        self.tool_num_predict = max(1, int(tool_num_predict))
        self.require_mcp = require_mcp
        self.request_logger = request_logger

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        key = request.request_id or str(uuid4())
        self._log(key, "analyze_started", {"text": request.text})
        prompt_name = request.prompt_name or self.default_prompt
        system_prompt_name = request.system_prompt_name or self.default_system_prompt

        system_prompt_text = self.prompt_repository.load_prompt(system_prompt_name)
        prompt_text = self.prompt_repository.load_prompt(prompt_name)

        if "${USER_TEXT}" in prompt_text:
            message = prompt_text.replace("${USER_TEXT}", request.text)
        else:
            message = f"{prompt_text}\n\nUser: {request.text}\nAssistant:"

        rdf, mcp_calls = self._generate_valid_rdf(
            system_prompt=system_prompt_text,
            prompt=message,
            max_attempts=request.max_rdf_attempts,
            key=key,
        )

        response = AnalyzeResponse(
            text=request.text,
            rdf=rdf,
            prompt_name=prompt_name,
            system_prompt_name=system_prompt_name,
            mcp_calls=mcp_calls,
        )
        self._log(
            key,
            "analyze_completed",
            {
                "prompt_name": prompt_name,
                "system_prompt_name": system_prompt_name,
                "rdf": rdf,
                "mcp_call_count": len(mcp_calls),
            },
        )
        return response

    def health(self) -> dict[str, dict[str, Any]]:
        return {"ollama": self.llm.health_check(), "wikidata_mcp": self.wikidata.health()}

    def _generate_valid_rdf(
        self,
        system_prompt: str,
        prompt: str,
        max_attempts: int,
        key: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        attempts = max(1, min(max_attempts, 3))
        last_error: str | None = None
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        mcp_calls = self._gather_evidence(messages, key) if self.require_mcp else []

        for attempt in range(1, attempts + 1):
            assistant = self._chat(messages, key, attempt, tools=None)
            messages.append(assistant)
            model_response = assistant["content"].strip()

            try:
                if assistant.get("tool_calls"):
                    raise ValueError("Ollama requested tools during RDF generation.")
                rdf_text = model_response_to_turtle(model_response)
                self._log(
                    key,
                    "rdf_validated",
                    {"attempt": attempt, "validation_method": "strict"},
                )
                return rdf_text, mcp_calls
            except ValueError as exc:
                last_error = str(exc)
                self._log(
                    key,
                    "rdf_validation_failed",
                    {"attempt": attempt, "error": last_error},
                )

            if attempt == attempts:
                break
            messages.append(
                {
                    "role": "user",
                    "content": self._build_retry_prompt(
                        model_response, last_error or "Invalid structured RDF response."
                    ),
                }
            )

        raise RDFValidationError(
            "RDF parsing failed.",
            attempts=attempts,
            last_error=last_error,
        )

    def _gather_evidence(self, messages: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        tools = self.wikidata.ollama_tools()
        executed: list[dict[str, Any]] = []
        reminded = False
        for round_number in range(1, self.max_tool_rounds + 1):
            assistant = self._chat(messages, key, round_number, tools=tools)
            requested_calls = assistant.get("tool_calls") or []
            if not isinstance(requested_calls, list):
                raise RuntimeError("Ollama returned malformed tool calls.")
            tool_calls = requested_calls[: self.max_tool_calls - len(executed)]
            if tool_calls:
                assistant["tool_calls"] = tool_calls
            messages.append(assistant)

            if not tool_calls:
                if executed:
                    break
                if reminded:
                    raise RuntimeError(
                        "The configured Ollama model did not call the required Wikidata MCP tools."
                    )
                reminded = True
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Use the available Wikidata tools before answering. Search each "
                            "recognizable entity and inspect its instance/subclass hierarchy."
                        ),
                    }
                )
                continue

            for tool_call in tool_calls:
                name, arguments = _tool_call_parts(tool_call)
                result = self.wikidata.call_tool(name, arguments)
                audit = {"name": name, "arguments": arguments, "result": _truncate(result, 6000)}
                self._log(key, "wikidata_tool_result", audit)
                executed.append(audit)
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": _truncate(result, self.max_tool_result_chars),
                    }
                )
            if len(executed) == self.max_tool_calls:
                break
        else:
            raise RuntimeError("Ollama exceeded the configured MCP tool-call round limit.")

        messages.append(
            {
                "role": "user",
                "content": (
                    "Tool gathering is complete. Using the evidence already returned, "
                    "return only a JSON object with an rdf field containing the complete Turtle string. "
                    "Do not call more tools."
                ),
            }
        )
        return executed

    def _chat(
        self,
        messages: list[dict[str, Any]],
        key: str,
        round_number: int,
        *,
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        self._log(
            key,
            "llm_chat_request",
            {
                "round": round_number,
                "phase": "grounding" if tools else "generation",
                "messages": messages,
                "tools_enabled": bool(tools),
            },
        )
        generation = self.llm.chat(
            messages=messages,
            tools=tools,
            num_predict=self.tool_num_predict if tools else None,
            response_format=None if tools else RDF_RESPONSE_SCHEMA,
        )
        self._log(key, "llm_chat_response", {"round": round_number, "response": generation})
        assistant = generation.get("message")
        if not isinstance(assistant, dict):
            raise RuntimeError("Ollama response does not contain an assistant message.")
        normalized = {"role": "assistant", "content": str(assistant.get("content") or "")}
        if assistant.get("tool_calls"):
            normalized["tool_calls"] = assistant["tool_calls"]
        return normalized

    @staticmethod
    def _build_retry_prompt(invalid_response: str, parser_error: str) -> str:
        error = parser_error[:1200]
        previous = invalid_response[:3000]
        return (
            "The previous RDF response was empty or invalid.\n"
            f"Validation error:\n{error}\n\n"
            'Return the complete corrected JSON object {"rdf": "<Turtle string>"}. '
            "The Turtle must declare rdfs, wd and kg with the namespaces specified in the prompt, "
            "contain triples and a relationship beyond labels. Escape newlines and quotes for JSON. "
            "Return JSON only, without Markdown or explanations. Do not call more tools.\n"
            f"Previous invalid response:\n{previous}"
        )

    def _log(self, key: str, event: str, payload: dict[str, Any]) -> None:
        if self.request_logger:
            self.request_logger.log(request_id=key, event=event, payload=payload)


def _tool_call_parts(tool_call: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(tool_call, dict) or not isinstance(tool_call.get("function"), dict):
        raise RuntimeError("Ollama returned a malformed tool call.")
    function = tool_call["function"]
    name = function.get("name")
    if not isinstance(name, str) or not name:
        raise RuntimeError("Ollama returned a tool call without a function name.")
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ollama returned invalid arguments for tool {name!r}.") from exc
    if not isinstance(arguments, dict):
        raise RuntimeError(f"Ollama returned non-object arguments for tool {name!r}.")
    return name, arguments


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…"
