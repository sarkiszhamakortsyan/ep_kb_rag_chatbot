"""Application settings, loaded from environment variables (and `.env` for local runs)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.pricing import ModelPrice, PriceTable
from app.rag.chunking import ChunkingConfig

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
    ollama_chat_model: str = "ministral-3:3b"
    ollama_embed_model: str = "embeddinggemma"
    ollama_num_ctx: int = Field(default=4096, ge=512)
    ollama_keep_alive: str = "30m"
    # None = don't send `think`; set false for thinking models (e.g. qwen3) to cut CPU latency.
    ollama_think: bool | None = None
    # Max wait for the first token / between tokens (prompt processing is slow on CPU)
    ollama_timeout_s: float = Field(default=300.0, gt=0)

    # Anthropic (bring your own key)
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5"
    # None = API default (high). "low"/"medium" cut latency and cost for simple Q&A.
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    # Server-side fallback when the model's safety classifiers decline a request.
    anthropic_refusal_fallback: bool = True

    # Knowledge base and index cache (relative to the backend directory)
    kb_dir: Path = Path("data/kb")
    index_dir: Path = Path("data/index")
    chunk_max_words: int = Field(default=300, ge=50)
    chunk_overlap_words: int = Field(default=45, ge=0)

    # Retrieval
    top_k: int = Field(default=6, ge=1, le=20)
    min_score: float = Field(default=0.35, ge=-1.0, le=1.0)

    # API
    # Browser origins allowed to call the API directly (the Vite dev server). In Docker the
    # frontend is served from the same origin via nginx, so no CORS is needed there.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: str = "INFO"

    # Admin area (hidden tabs: history, stats, ...). Disabled when empty.
    admin_token: SecretStr | None = None

    # Response history (ideas.md #5): every turn is stored in SQLite for the admin area.
    history_enabled: bool = True
    history_retention_days: int = Field(default=90, ge=1)
    database_path: Path = Path("data/db/history.sqlite")

    # Costs tab (ideas.md #2): USD per million tokens, as JSON, e.g. MODEL_PRICES=
    # {"claude-opus-5": {"input": 5, "output": 25, "cache_read": 0.5, "cache_write": 6.25}}
    model_prices: dict[str, ModelPrice] = {}
    # Optional cost of running the local model, e.g. a GPU server's price per hour (USD).
    local_cost_per_hour: float = Field(default=0.0, ge=0)

    @field_validator("enabled_llm_providers", "cors_origins", mode="before")
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

    def price_table(self) -> PriceTable:
        return PriceTable(self.model_prices, self.local_cost_per_hour)

    def chunking(self) -> ChunkingConfig:
        return ChunkingConfig(
            max_words=self.chunk_max_words, overlap_words=self.chunk_overlap_words
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
