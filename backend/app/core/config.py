"""Application settings, loaded from environment variables (and `.env` for local runs)."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LLMProviderName = Literal["ollama", "anthropic"]
EmbeddingProviderName = Literal["ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repo-root .env when running from backend/, local .env otherwise; env vars win.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM / embedding provider selection (ideas.md #7: enable/disable models)
    llm_provider: LLMProviderName = "ollama"
    enabled_llm_providers: Annotated[list[LLMProviderName], NoDecode] = ["ollama", "anthropic"]
    embedding_provider: EmbeddingProviderName = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "gemma3:4b"
    ollama_embed_model: str = "embeddinggemma"
    ollama_num_ctx: int = Field(default=4096, ge=512)
    ollama_keep_alive: str = "30m"
    # None = don't send `think`; set false for thinking models (e.g. qwen3) to cut CPU latency.
    ollama_think: bool | None = None

    # Anthropic (bring your own key)
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5"
    # None = API default (high). "low"/"medium" cut latency and cost for simple Q&A.
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    # Server-side fallback when the model's safety classifiers decline a request.
    anthropic_refusal_fallback: bool = True

    # Retrieval
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.35, ge=-1.0, le=1.0)

    # Admin area (future hidden tabs); disabled when empty
    admin_token: SecretStr | None = None

    @field_validator("enabled_llm_providers", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "anthropic_api_key", "admin_token", "ollama_think", "anthropic_effort", mode="before"
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def _default_provider_enabled(self) -> "Settings":
        if self.llm_provider not in self.enabled_llm_providers:
            raise ValueError(
                f"LLM_PROVIDER={self.llm_provider!r} is not in ENABLED_LLM_PROVIDERS "
                f"{self.enabled_llm_providers}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
