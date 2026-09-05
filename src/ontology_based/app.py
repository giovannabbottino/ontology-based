from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from .application.services import OntologyKnowledgeGraphService
from .controllers.analyze_controller import create_analyze_blueprint
from .infrastructure import (
    OllamaChatClient,
    OllamaClientConfig,
    PromptRepository,
    RequestLogger,
    WikidataMCPClient,
    WikidataMCPConfig,
)

DEFAULT_PROMPT_NAME = "prompts/ontology-few-shot.txt"
DEFAULT_SYSTEM_PROMPT_NAME = "system/knowledge_graph.txt"


def create_app() -> Flask:
    load_dotenv()
    app = Flask(__name__)

    analyze_log_path = os.getenv("ANALYZE_LOG_PATH", "data/analyze_log.jsonl")
    request_logger = RequestLogger(Path(analyze_log_path)) if analyze_log_path else None

    service = OntologyKnowledgeGraphService(
        prompt_repository=PromptRepository(),
        default_prompt=os.getenv("DEFAULT_PROMPT_NAME", DEFAULT_PROMPT_NAME),
        default_system_prompt=os.getenv("DEFAULT_SYSTEM_PROMPT_NAME", DEFAULT_SYSTEM_PROMPT_NAME),
        llm=OllamaChatClient(OllamaClientConfig.from_env()),
        wikidata=WikidataMCPClient(WikidataMCPConfig.from_env()),
        max_tool_rounds=_int_env("MAX_TOOL_ROUNDS", 8),
        max_tool_calls=_int_env("MAX_TOOL_CALLS", 4),
        max_tool_result_chars=_int_env("MAX_TOOL_RESULT_CHARS", 1500),
        tool_num_predict=_int_env("OLLAMA_TOOL_NUM_PREDICT", 256),
        require_mcp=_bool_env("REQUIRE_WIKIDATA_MCP", True),
        request_logger=request_logger,
    )
    app.register_blueprint(create_analyze_blueprint(service))
    return app


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def main() -> None:
    create_app().run(host="127.0.0.1", port=5100, debug=True)


if __name__ == "__main__":
    main()
