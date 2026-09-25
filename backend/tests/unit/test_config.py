import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_defaults() -> None:
    settings = make()
    assert settings.llm_provider == "ollama"
    assert settings.enabled_llm_providers == ["ollama", "anthropic"]
    assert settings.anthropic_api_key is None


def test_enabled_providers_parsed_from_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLED_LLM_PROVIDERS", " anthropic , ")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert make().enabled_llm_providers == ["anthropic"]


def test_empty_env_values_become_none(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "ADMIN_TOKEN", "OLLAMA_THINK", "ANTHROPIC_EFFORT"):
        monkeypatch.setenv(name, "")
    settings = make()
    assert settings.anthropic_api_key is None
    assert settings.admin_token is None
    assert settings.ollama_think is None
    assert settings.anthropic_effort is None


def test_default_provider_must_be_enabled() -> None:
    with pytest.raises(ValidationError, match="not in ENABLED_LLM_PROVIDERS"):
        make(llm_provider="anthropic", enabled_llm_providers=["ollama"])


def test_unknown_provider_rejected() -> None:
    with pytest.raises(ValidationError):
        make(enabled_llm_providers=["ollama", "gpt"])


def test_api_key_is_not_printed() -> None:
    settings = make(anthropic_api_key="sk-ant-secret")
    assert "sk-ant-secret" not in repr(settings)
