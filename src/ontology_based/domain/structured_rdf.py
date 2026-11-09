from __future__ import annotations

import json
from typing import Any

from rdflib import Graph
from rdflib.namespace import RDFS

RDF_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"rdf": {"type": "string", "minLength": 1}},
    "required": ["rdf"],
    "additionalProperties": False,
}
REQUIRED_PREFIXES = {
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "wd": "http://www.wikidata.org/entity/",
    "kg": "https://example.org/wikidata-description/",
}


def model_response_to_turtle(response_text: str) -> str:
    """Extract and validate the model's JSON-wrapped Turtle without repairing it."""
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid RDF JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict) or set(payload) != {"rdf"}:
        raise ValueError("Model response must be a JSON object containing only the 'rdf' field.")
    rdf = payload["rdf"]
    if not isinstance(rdf, str) or not rdf.strip():
        raise ValueError("Field 'rdf' must be a non-empty Turtle string.")
    rdf = rdf.strip()
    try:
        graph = Graph(bind_namespaces="none").parse(data=rdf, format="turtle")
    except Exception as exc:  # RDFLib exposes parser-specific exception classes.
        raise ValueError(f"Invalid Turtle: {exc}") from exc
    if not graph:
        raise ValueError("RDF response contains no triples.")
    namespaces = dict(graph.namespaces())
    for prefix, namespace in REQUIRED_PREFIXES.items():
        if str(namespaces.get(prefix, "")) != namespace:
            raise ValueError(f"RDF must declare @prefix {prefix}: <{namespace}> .")
    if not any(predicate != RDFS.label for _, predicate, _ in graph):
        raise ValueError("RDF response contains labels but no semantic relationships.")
    return rdf
