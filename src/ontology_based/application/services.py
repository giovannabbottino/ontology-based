from __future__ import annotations

import json
from typing import Any, Protocol

from rdflib import Graph
from rdflib.namespace import RDFS

from ..domain.models import AnalyzeRequest, AnalyzeResponse


class PromptLoader(Protocol):
    def load_prompt(self, prompt_name: str) -> str: ...


class ChatClient(Protocol):
    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
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
        require_mcp: bool = True,
    ) -> None:
        self.prompt_repository = prompt_repository
        self.default_prompt = default_prompt
        self.default_system_prompt = default_system_prompt
        self.llm = llm
        self.wikidata = wikidata
        self.max_tool_rounds = max(1, int(max_tool_rounds))
        self.require_mcp = require_mcp

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        prompt_name = request.prompt_name or self.default_prompt
        system_prompt_name = request.system_prompt_name or self.default_system_prompt

        system_prompt_text = self.prompt_repository.load_prompt(system_prompt_name)
        prompt_text = self.prompt_repository.load_prompt(prompt_name)

        if "${USER_TEXT}" in prompt_text or "${Text_TEXT}" in prompt_text:
            message = prompt_text.replace("${USER_TEXT}", request.text).replace("${Text_TEXT}", request.text)
        else:
            message = f"{prompt_text}\n\nUser: {request.text}\nAssistant:"

        rdf, mcp_calls = self._generate_valid_rdf(
            system_prompt=system_prompt_text,
            prompt=message,
            max_attempts=request.max_rdf_attempts,
        )

        return AnalyzeResponse(
            text=request.text,
            rdf=rdf,
            prompt_name=prompt_name,
            system_prompt_name=system_prompt_name,
            mcp_calls=mcp_calls,
        )

    def health(self) -> dict[str, dict[str, Any]]:
        return {"ollama": self.llm.health_check(), "wikidata_mcp": self.wikidata.health()}

    def _generate_valid_rdf(
        self,
        system_prompt: str,
        prompt: str,
        max_attempts: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        attempts = max(1, min(int(max_attempts or 3), 3))
        last_error: str | None = None
        tools = self.wikidata.ollama_tools()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        mcp_calls: list[dict[str, Any]] = []

        for attempt in range(1, attempts + 1):
            rdf_text, calls = self._chat_until_answer(
                messages,
                tools,
                require_tool_call=self.require_mcp and not mcp_calls,
            )
            mcp_calls.extend(calls)

            try:
                self._parse_rdf(rdf_text)
                return rdf_text, mcp_calls
            except Exception as exc:  # rdflib raises parser-specific exception classes.
                last_error = str(exc)

            if attempt == attempts:
                break
            messages.append(
                {
                    "role": "user",
                    "content": self._build_retry_prompt(prompt, rdf_text, last_error or "Invalid Turtle RDF."),
                }
            )

        raise RDFValidationError(
            "RDF parsing failed.",
            attempts=attempts,
            last_error=last_error,
        )

    def _chat_until_answer(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        require_tool_call: bool,
    ) -> tuple[str, list[dict[str, Any]]]:
        executed: list[dict[str, Any]] = []
        reminded = False
        for _ in range(self.max_tool_rounds):
            generation = self.llm.chat(messages=messages, tools=tools)
            assistant = generation.get("message")
            if not isinstance(assistant, dict):
                raise RuntimeError("Ollama response does not contain an assistant message.")
            messages.append(_assistant_message(assistant))

            tool_calls = assistant.get("tool_calls") or []
            if tool_calls:
                for tool_call in tool_calls:
                    name, arguments = _tool_call_parts(tool_call)
                    result = self.wikidata.call_tool(name, arguments)
                    executed.append(
                        {
                            "name": name,
                            "arguments": arguments,
                            "result": _truncate(result, 6000),
                        }
                    )
                    messages.append({"role": "tool", "tool_name": name, "content": result})
                continue

            if require_tool_call and not executed:
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
                            "recognizable entity and inspect its instance/subclass hierarchy; "
                            "then return only Turtle."
                        ),
                    }
                )
                continue

            content = str(assistant.get("content") or "")
            return self._extract_rdf_text(content), executed

        raise RuntimeError("Ollama exceeded the configured MCP tool-call round limit.")

    @staticmethod
    def _parse_rdf(rdf_text: str) -> None:
        if not rdf_text.strip():
            raise ValueError("Empty RDF response.")
        graph = Graph().parse(data=rdf_text, format="turtle")
        if len(graph) == 0:
            raise ValueError("RDF response contains no triples.")
        if not any(predicate != RDFS.label for _, predicate, _ in graph):
            raise ValueError("RDF response contains labels but no semantic relationships.")

    @staticmethod
    def _extract_rdf_text(response_text: str) -> str:
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        rdf_markers = ("@prefix", "@base", "PREFIX", "BASE", "<", "_:")
        starts = [idx for marker in rdf_markers if (idx := text.find(marker)) >= 0]
        if starts:
            text = text[min(starts) :].strip()
        return text

    @staticmethod
    def _build_retry_prompt(original_prompt: str, invalid_rdf: str, parser_error: str) -> str:
        error = parser_error[:1200]
        previous = invalid_rdf[:6000]
        return (
            f"{original_prompt}\n\n"
            "The previous answer was not valid Turtle RDF when parsed with rdflib Graph.parse.\n"
            f"Parser error:\n{error}\n\n"
            "Return only corrected valid Turtle RDF. Do not include markdown fences, "
            "comments, or explanations. Every predicate must have an object; separate "
            "multiple objects with commas; use kg: resources instead of wd:Q?; never "
            "emit a standalone period.\n"
            f"Previous invalid RDF:\n{previous}"
        )


def _assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "role": "assistant",
        "content": str(message.get("content") or ""),
    }
    if message.get("tool_calls"):
        normalized["tool_calls"] = message["tool_calls"]
    return normalized


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
