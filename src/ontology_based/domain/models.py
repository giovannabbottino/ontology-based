from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnalyzeRequest:
    text: str
    idempotence_key: str | None = None
    prompt_name: str | None = None
    system_prompt_name: str | None = None
    max_rdf_attempts: int = 3


@dataclass(frozen=True)
class AnalyzeResponse:
    text: str
    rdf: str
    prompt_name: str
    system_prompt_name: str
    mcp_calls: list[dict[str, Any]] = field(default_factory=list)
    source_attribution: str = "Source: Wikidata MCP"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "rdf": self.rdf,
            "prompt_name": self.prompt_name,
            "system_prompt_name": self.system_prompt_name,
            "source_attribution": self.source_attribution,
            "mcp_calls": self.mcp_calls,
        }
