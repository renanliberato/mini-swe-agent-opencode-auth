from minisweagent_opencode_auth.cli import build_environment, parse_selector


def test_selector_parses_explicit_provider_model_and_effort():
    assert parse_selector("codex:gpt-5.6-luna@high").__dict__ == {
        "provider": "codex",
        "model": "gpt-5.6-luna",
        "effort": "high",
    }


def test_provider_alias_is_normalized():
    assert parse_selector("go:glm-5.2@low").provider == "opencode-go"
    assert parse_selector("zai:glm-5.2").provider == "glm"


def test_environment_maps_selector_to_adapter_variables():
    environment = build_environment(parse_selector("glm:glm-5.2@medium"), {"PATH": "/bin"})
    assert environment["MSWEA_SUBSCRIPTION"] == "glm"
    assert environment["MSWEA_GLM_MODEL"] == "glm-5.2"
    assert environment["MSWEA_REASONING_EFFORT"] == "medium"
    assert environment["PATH"] == "/bin"
