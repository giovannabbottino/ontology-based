from ontology_based.config import AppConfig


def clear_config_environment(monkeypatch):
    import os

    for name in os.environ:
        if name.startswith(("OLLAMA_", "WIKIDATA_", "DEFAULT_", "MAX_TOOL_")) or name in {
            "ANALYZE_LOG_PATH",
            "REQUIRE_WIKIDATA_MCP",
        }:
            monkeypatch.delenv(name)


def test_environment_defaults_match_configuration_defaults(monkeypatch):
    clear_config_environment(monkeypatch)
    assert AppConfig.from_env() == AppConfig()


def test_loads_environment_for_both_clients_and_service(monkeypatch):
    clear_config_environment(monkeypatch)
    for name, value in {
        "REQUIRE_WIKIDATA_MCP": "false",
        "MAX_TOOL_CALLS": "2",
        "OLLAMA_MODEL": "test-model",
        "OLLAMA_TEMPERATURE": "0",
        "OLLAMA_SEED": "42",
        "OLLAMA_STOP": "END",
        "OLLAMA_TIMEOUT_SECONDS": "10.5",
        "WIKIDATA_MCP_TOOLS": "search_items, custom_tool, ",
        "WIKIDATA_LANGUAGE": "pt",
        "ANALYZE_LOG_PATH": "",
    }.items():
        monkeypatch.setenv(name, value)
    config = AppConfig.from_env()
    assert not config.require_mcp
    assert config.max_tool_calls == 2
    assert config.ollama.model == "test-model"
    assert config.ollama.options == {**AppConfig().ollama.options, "stop": "END"}
    assert config.ollama.timeout_seconds == 10.5
    assert config.wikidata.allowed_tools == ("search_items", "custom_tool")
    assert config.wikidata.language == "pt"
    assert config.analyze_log_path == ""


def test_invalid_numeric_environment_uses_defaults(monkeypatch):
    clear_config_environment(monkeypatch)
    for name in ("MAX_TOOL_CALLS", "OLLAMA_TIMEOUT_SECONDS", "WIKIDATA_TIMEOUT_SECONDS", "OLLAMA_SEED"):
        monkeypatch.setenv(name, "invalid")
    assert AppConfig.from_env() == AppConfig()


def test_zero_and_negative_tool_limits_are_clamped_to_one(monkeypatch):
    clear_config_environment(monkeypatch)
    monkeypatch.setenv("MAX_TOOL_CALLS", "0")
    monkeypatch.setenv("MAX_TOOL_ROUNDS", "-1")
    config = AppConfig.from_env()
    assert config.max_tool_calls == 1
    assert config.max_tool_rounds == 1


def test_dotenv_example_contains_requested_generation_settings_and_log_paths():
    from pathlib import Path

    from dotenv import dotenv_values

    settings = dotenv_values(Path(".env.example"))
    assert {
        name: settings[name]
        for name in (
            "OLLAMA_SEED",
            "OLLAMA_TEMPERATURE",
            "OLLAMA_TOP_K",
            "OLLAMA_TOP_P",
            "OLLAMA_MIN_P",
            "OLLAMA_NUM_PREDICT",
            "OLLAMA_TIMEOUT_SECONDS",
        )
    } == {
        "OLLAMA_SEED": "42",
        "OLLAMA_TEMPERATURE": "0",
        "OLLAMA_TOP_K": "1",
        "OLLAMA_TOP_P": "1",
        "OLLAMA_MIN_P": "0",
        "OLLAMA_NUM_PREDICT": "2048",
        "OLLAMA_TIMEOUT_SECONDS": "300",
    }
    assert settings["OLLAMA_JSONL_PATH"] == "logs/ollama_responses.jsonl"
    assert settings["ANALYZE_LOG_PATH"] == "logs/analyze_log.jsonl"
