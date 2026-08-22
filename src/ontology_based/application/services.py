from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterator
from typing import Any, Protocol

from rdflib import Graph, Namespace
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

            for _repair_method, candidate_rdf in self._rdf_repair_candidates(
                rdf_text, include_salvage=attempt == attempts
            ):
                try:
                    self._parse_rdf(candidate_rdf)
                    return candidate_rdf, mcp_calls
                except Exception as exc:  # rdflib raises parser-specific exception classes.
                    last_error = str(exc)

            if attempt == attempts:
                break
            messages.append(
                {
                    "role": "user",
                    "content": self._build_retry_prompt("", rdf_text, last_error or "Invalid Turtle RDF."),
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

    @classmethod
    def _rdf_repair_candidates(
        cls, rdf_text: str, *, include_salvage: bool = True
    ) -> Iterator[tuple[str, str]]:
        raw = (rdf_text or "").strip().replace("\r\n", "\n").replace("\r", "\n")
        raw = raw.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
        raw = re.sub(r'""([^"\n]+)""', r'"\1"', raw)

        seen: set[str] = set()

        def emit(method: str, value: str) -> Iterator[tuple[str, str]]:
            value = (value or "").strip()
            if not value or value in seen:
                return
            seen.add(value)
            yield method, value

        yield from emit("trim", raw)

        normalized = cls._normalize_common_turtle_errors(raw)
        yield from emit("normalize_common_turtle_errors", normalized)

        if raw and not raw.endswith("."):
            yield from emit("append_final_dot", raw + " .")

        if raw and not raw.endswith("."):
            lines = raw.splitlines()
            last_complete_line = None
            for idx, line in enumerate(lines):
                if line.strip().endswith("."):
                    last_complete_line = idx
            if last_complete_line is not None:
                yield from emit(
                    "keep_through_last_complete_statement",
                    "\n".join(lines[: last_complete_line + 1]),
                )

            blocks = re.split(r"\n\s*\n", raw)
            if len(blocks) > 1:
                candidate = "\n\n".join(blocks[:-1]).strip()
                if candidate and not candidate.endswith("."):
                    candidate += " ."
                yield from emit("drop_incomplete_last_block", candidate)

        if include_salvage:
            salvaged = cls._salvage_parseable_statements(normalized)
            yield from emit("salvage_parseable_statements", salvaged)

    @classmethod
    def _normalize_common_turtle_errors(cls, rdf_text: str) -> str:
        text = re.sub(r"(?m)^\s*\.\s*$", "", rdf_text).strip()
        text = re.sub(
            r'wd:Q(?:\?|[0-9]*,[0-9,]*)\s+rdfs:label\s+"([^"]+)"(@[A-Za-z-]+)?',
            cls._replace_invalid_wikidata_label_subject,
            text,
        )
        if re.search(r"\bxsd:", text) and not re.search(r"(?im)^\s*(?:@prefix|prefix)\s+xsd:", text):
            text = "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n" + text
        return text.strip()

    @classmethod
    def _replace_invalid_wikidata_label_subject(cls, match: re.Match[str]) -> str:
        label = match.group(1)
        language = match.group(2) or ""
        return f'kg:{cls._safe_local_name(label)} rdfs:label "{label}"{language}'

    @staticmethod
    def _safe_local_name(label: str) -> str:
        normalized = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
        local_name = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").lower()
        if not local_name:
            local_name = "unknown_entity"
        if local_name[0].isdigit():
            local_name = f"entity_{local_name}"
        return local_name

    @classmethod
    def _salvage_parseable_statements(cls, rdf_text: str) -> str:
        prefix_lines: list[str] = []
        body_lines: list[str] = []
        for line in rdf_text.splitlines():
            if re.match(r"^\s*(?:@prefix|prefix)\s+", line, flags=re.IGNORECASE):
                prefix_lines.append(line.strip())
            else:
                body_lines.append(line)

        prefix_text = "\n".join(prefix_lines)
        statements: list[str] = []
        current: list[str] = []
        for line in body_lines:
            stripped = line.strip()
            if not stripped:
                continue
            current.append(stripped)
            if stripped.endswith("."):
                statements.append("\n".join(current))
                current = []

        graph = Graph()
        graph.bind("rdfs", RDFS)
        graph.bind("wd", Namespace("http://www.wikidata.org/entity/"))
        graph.bind("kg", Namespace("https://example.org/wikidata-description/"))
        graph.bind("xsd", Namespace("http://www.w3.org/2001/XMLSchema#"))

        for statement in statements:
            parsed = cls._try_parse_statement(prefix_text, statement)
            if parsed is not None:
                graph += parsed
                continue

            compact = statement.rstrip().removesuffix(".").strip()
            clauses = re.split(r"\s*;\s*", compact)
            first_match = re.match(r"^(\S+)\s+(.+)$", clauses[0], flags=re.DOTALL)
            if first_match is None:
                continue
            subject = first_match.group(1)
            clause_statements = [
                clauses[0],
                *(f"{subject} {clause}" for clause in clauses[1:]),
            ]
            for clause_statement in clause_statements:
                parsed = cls._try_parse_statement(prefix_text, clause_statement + " .")
                if parsed is None and '"' not in clause_statement:
                    terms = clause_statement.split()
                    if len(terms) > 3:
                        parsed = cls._try_parse_statement(prefix_text, " ".join(terms[:3]) + " .")
                if parsed is not None:
                    graph += parsed

        if not graph:
            return ""
        return str(graph.serialize(format="turtle")).strip()

    @staticmethod
    def _try_parse_statement(prefix_text: str, statement: str) -> Graph | None:
        try:
            return Graph().parse(data=f"{prefix_text}\n{statement}", format="turtle")
        except Exception:
            return None

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
