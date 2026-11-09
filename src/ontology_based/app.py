from __future__ import annotations

from dotenv import load_dotenv
from flask import Flask

from .application.services import OntologyKnowledgeGraphService
from .config import AppConfig
from .controllers.analyze_controller import create_analyze_blueprint
from .infrastructure.ollama_client import OllamaChatClient
from .infrastructure.prompt_repository import PromptRepository
from .infrastructure.request_logger import RequestLogger
from .infrastructure.wikidata_mcp_client import WikidataMCPClient


def create_app() -> Flask:
    load_dotenv()
    config = AppConfig.from_env()
    app = Flask(__name__)
    service = OntologyKnowledgeGraphService(
        prompt_repository=PromptRepository(),
        default_prompt=config.default_prompt,
        default_system_prompt=config.default_system_prompt,
        llm=OllamaChatClient(config.ollama),
        wikidata=WikidataMCPClient(config.wikidata),
        max_tool_rounds=config.max_tool_rounds,
        max_tool_calls=config.max_tool_calls,
        max_tool_result_chars=config.max_tool_result_chars,
        tool_num_predict=config.tool_num_predict,
        require_mcp=config.require_mcp,
        request_logger=RequestLogger(config.analyze_log_path),
    )
    app.register_blueprint(create_analyze_blueprint(service))
    return app


def main() -> None:
    create_app().run(host="127.0.0.1", port=5100, debug=True)
