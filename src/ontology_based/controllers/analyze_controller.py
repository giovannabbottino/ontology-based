from __future__ import annotations

from typing import Any, Protocol

import requests
from flask import Blueprint, jsonify, request

from ..application.services import RDFValidationError
from ..domain.models import AnalyzeRequest, AnalyzeResponse


class AnalyzeService(Protocol):
    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse: ...

    def health(self) -> dict[str, Any]: ...


def create_analyze_blueprint(service: AnalyzeService) -> Blueprint:
    blueprint = Blueprint("analyze", __name__)

    @blueprint.get("/health")
    def health() -> tuple:
        status = service.health()
        ok = all(part.get("status") == "ok" for part in status.values())
        return jsonify(status), 200 if ok else 503

    @blueprint.post("/analyze")
    def analyze() -> tuple:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object."}), 400
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return jsonify({"error": "Field 'text' is required."}), 400

        prompt_name = payload.get("prompt_name")
        system_prompt_name = payload.get("system_prompt_name")
        idempotence_key = payload.get("idempotence_key")
        max_attempts = payload.get("max_rdf_attempts", 3)
        if prompt_name is not None and not isinstance(prompt_name, str):
            return jsonify({"error": "Field 'prompt_name' must be a string."}), 400
        if system_prompt_name is not None and not isinstance(system_prompt_name, str):
            return jsonify({"error": "Field 'system_prompt_name' must be a string."}), 400
        if idempotence_key is not None and not isinstance(idempotence_key, str):
            return jsonify({"error": "Field 'idempotence_key' must be a string."}), 400
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
            return jsonify({"error": "Field 'max_rdf_attempts' must be an integer."}), 400

        try:
            response = service.analyze(
                AnalyzeRequest(
                    text=text.strip(),
                    idempotence_key=idempotence_key,
                    prompt_name=prompt_name,
                    system_prompt_name=system_prompt_name,
                    max_rdf_attempts=max_attempts,
                )
            )
        except FileNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except requests.Timeout as exc:
            return jsonify({"error": "External service request timed out.", "details": str(exc)}), 504
        except requests.RequestException as exc:
            return jsonify({"error": "External service request failed.", "details": str(exc)}), 502
        except RDFValidationError as exc:
            return (
                jsonify(
                    {
                        "error": "RDF parsing failed.",
                        "attempts": exc.attempts,
                        "details": exc.last_error,
                    }
                ),
                422,
            )
        except (RuntimeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 502

        return jsonify(response.to_dict()), 200

    return blueprint
