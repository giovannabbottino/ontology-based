from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask

from .application.services import OntologyKnowledgeGraphService
from .controllers.analyze_controller import create_analyze_blueprint
from .infrastructure import (
    OllamaChatClient,
    OllamaClientConfig,
    PromptRepository,
    WikidataMCPClient,
    WikidataMCPConfig,
)

DEFAULT_PROMPT_NAME = "prompts/ontology-few-shot.txt"
DEFAULT_SYSTEM_PROMPT_NAME = "system/knowledge_graph.txt"


def create_app() -> Flask:
    load_dotenv()
    app = Flask(__name__)

    service = OntologyKnowledgeGraphService(
        prompt_repository=PromptRepository(),
        default_prompt=os.getenv("DEFAULT_PROMPT_NAME", DEFAULT_PROMPT_NAME),
        default_system_prompt=os.getenv("DEFAULT_SYSTEM_PROMPT_NAME", DEFAULT_SYSTEM_PROMPT_NAME),
        llm=OllamaChatClient(OllamaClientConfig.from_env()),
        wikidata=WikidataMCPClient(WikidataMCPConfig.from_env()),
        max_tool_rounds=_int_env("MAX_TOOL_ROUNDS", 8),
        require_mcp=_bool_env("REQUIRE_WIKIDATA_MCP", True),
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
