import pytest

from app.core.config import Settings
from app.providers.embeddings.registry import build_embedding_registry
from app.providers.errors import ProviderConfigError, ProviderDisabledError, UnknownProviderError
from app.providers.llm.anthropic import AnthropicLLMProvider
from app.providers.llm.ollama import OllamaLLMProvider
from app.providers.llm.registry import build_llm_registry
from app.providers.registry import ProviderRegistry
from tests.fakes import FakeLLM


def make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_default_provider_is_returned_and_cached() -> None:
    registry = build_llm_registry(make())
    provider = registry.get()
    assert isinstance(provider, OllamaLLMProvider)
    assert registry.get("ollama") is provider


def test_named_provider() -> None:
    registry = build_llm_registry(make(anthropic_api_key="sk-test"))
    provider = registry.get("anthropic")
    assert isinstance(provider, AnthropicLLMProvider)
    assert provider.model == "claude-opus-5"


def test_disabled_provider_is_rejected() -> None:
    registry = build_llm_registry(make(enabled_llm_providers=["ollama"]))
    assert registry.enabled == ["ollama"]
    with pytest.raises(ProviderDisabledError, match="anthropic"):
        registry.get("anthropic")


def test_unknown_provider_is_rejected() -> None:
    registry = build_llm_registry(make())
    with pytest.raises(UnknownProviderError, match="gpt"):
        registry.get("gpt")


def test_missing_anthropic_key_fails_only_when_used() -> None:
    registry = build_llm_registry(make())  # app can start without a key
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        registry.get("anthropic")


def test_registry_rejects_enabled_provider_without_factory() -> None:
    with pytest.raises(UnknownProviderError):
        ProviderRegistry({"fake": FakeLLM}, enabled=["fake", "other"], default="fake")


def test_registry_rejects_disabled_default() -> None:
    with pytest.raises(ProviderDisabledError):
        ProviderRegistry({"a": FakeLLM, "b": FakeLLM}, enabled=["a"], default="b")


@pytest.mark.anyio
async def test_aclose_closes_created_providers() -> None:
    fake = FakeLLM()
    registry = ProviderRegistry({"fake": lambda: fake}, enabled=["fake"], default="fake")
    registry.get()
    await registry.aclose()
    assert fake.closed


def test_custom_factories_injected() -> None:
    registry = build_llm_registry(
        make(llm_provider="anthropic", enabled_llm_providers=["anthropic"]),
        factories={"anthropic": lambda s: FakeLLM(name="anthropic", model=s.anthropic_model)},
    )
    assert registry.get().model == "claude-opus-5"


def test_embedding_registry_uses_configured_provider() -> None:
    registry = build_embedding_registry(make())
    assert registry.enabled == ["ollama"]
    assert registry.get().model == "embeddinggemma"
