import json

import pytest
from rdflib import Graph

from ontology_based.domain.structured_rdf import REQUIRED_PREFIXES, model_response_to_turtle

PREFIXES = "".join(f"@prefix {prefix}: <{iri}> .\n" for prefix, iri in REQUIRED_PREFIXES.items())
TURTLE = PREFIXES + 'wd:Q7251 rdfs:label "Alan Turing"@en ; kg:is wd:Q5 .'


def test_extracts_valid_turtle_without_reserializing_or_losing_prefixes():
    turtle = model_response_to_turtle(json.dumps({"rdf": TURTLE}))
    assert turtle == TURTLE
    assert len(Graph().parse(data=turtle, format="turtle")) == 2


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"triples": []},
        {"rdf": None},
        {"rdf": 123},
        {"rdf": ""},
        {"rdf": "  "},
        {"rdf": TURTLE, "other": True},
    ],
)
def test_rejects_invalid_json_contract(payload):
    with pytest.raises(ValueError):
        model_response_to_turtle(json.dumps(payload))


@pytest.mark.parametrize("response", ["", "not json", TURTLE, '```json\n{"rdf": ""}\n```'])
def test_rejects_non_json_responses(response):
    with pytest.raises(ValueError, match="Invalid RDF JSON"):
        model_response_to_turtle(response)


@pytest.mark.parametrize(
    "turtle",
    [
        PREFIXES,
        PREFIXES + 'wd:Q7251 rdfs:label "Alan Turing"@en .',
        PREFIXES + "wd:Q7251 kg:is .",
        "wd:Q7251 kg:is wd:Q5 .",
    ],
)
def test_rejects_empty_graph_labels_only_and_invalid_turtle(turtle):
    with pytest.raises(ValueError):
        model_response_to_turtle(json.dumps({"rdf": turtle}))


@pytest.mark.parametrize("prefix", REQUIRED_PREFIXES)
def test_rejects_missing_or_incorrect_prefix_declarations(prefix):
    declaration = f"@prefix {prefix}: <{REQUIRED_PREFIXES[prefix]}> .\n"
    body = "<urn:alice> <urn:knows> <urn:bob> ."
    for replacement in ("", f"@prefix {prefix}: <https://wrong.example/> .\n"):
        with pytest.raises(ValueError, match=f"@prefix {prefix}"):
            model_response_to_turtle(json.dumps({"rdf": PREFIXES.replace(declaration, replacement) + body}))
