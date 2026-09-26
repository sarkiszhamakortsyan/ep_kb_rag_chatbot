"""Public API contract (v1). New optional fields may be added; existing ones won't change."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.rag.citations import Citation
from app.rag.pipeline import ChatOptions, ChatResult
from app.rag.prompts import LANGUAGES

MAX_MESSAGE_CHARS = 4000


class ChatOptionsIn(BaseModel):
    # Unknown options are rejected (422) instead of silently ignored.
    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(
        default=None, description="LLM provider for this question, e.g. 'ollama' or 'anthropic'."
    )
    detail: Literal["concise", "detailed"] = Field(
        default="concise", description="'detailed' asks for a complete explanation."
    )
    language: str | None = Field(
        default=None,
        description="Answer language (ISO 639-1 code, e.g. 'de'); omit to answer in the "
        "question's language.",
    )

    @field_validator("language")
    @classmethod
    def _known_language(cls, value: str | None) -> str | None:
        if value is not None and value not in LANGUAGES:
            raise ValueError(f"unsupported language; use one of {', '.join(LANGUAGES)}")
        return value

    def to_chat_options(self) -> ChatOptions:
        return ChatOptions(provider=self.provider, detail=self.detail, language=self.language)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: str | None = Field(
        default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$", description="Omit to start one."
    )
    options: ChatOptionsIn = Field(default_factory=ChatOptionsIn)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value.strip()


class CitationOut(BaseModel):
    number: int = Field(description="The [n] marker used in the answer.")
    chunk_id: str
    doc_id: str
    title: str
    section: str
    snippet: str
    score: float

    @classmethod
    def from_citation(cls, citation: Citation) -> "CitationOut":
        return cls(**citation.__dict__)


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class TimingsOut(BaseModel):
    embed_ms: float
    search_ms: float
    time_to_first_token_ms: float | None
    generation_ms: float
    total_ms: float
    rewrite_ms: float = 0.0


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    citations: list[CitationOut]
    refused: bool = Field(description="True when the knowledge base does not answer the question.")
    refusal_reason: Literal["low_score", "no_citations", "model_refusal"] | None
    provider: str | None
    model: str | None
    usage: UsageOut
    timings: TimingsOut
    top_score: float
    sources_used: int
    stop_reason: str | None
    language: str | None = Field(
        default=None, description="The requested answer language, if one was set."
    )
    standalone_question: str | None = Field(
        default=None,
        description="A follow-up rewritten as a self-contained question (what was answered).",
    )

    @classmethod
    def from_result(cls, result: ChatResult) -> "ChatResponse":
        return cls(
            conversation_id=result.conversation_id,
            message_id=result.message_id,
            answer=result.answer,
            citations=[CitationOut.from_citation(c) for c in result.citations],
            refused=result.refused,
            refusal_reason=result.refusal_reason,
            provider=result.provider,
            model=result.model,
            usage=UsageOut(**result.usage.__dict__),
            timings=TimingsOut(**result.timings.__dict__),
            top_score=round(result.top_score, 4),
            sources_used=result.sources_used,
            stop_reason=result.stop_reason,
            language=result.language,
            standalone_question=result.standalone_question,
        )


class ProviderOut(BaseModel):
    name: str
    model: str | None
    default: bool
    available: bool
    detail: str | None = None


class ProvidersResponse(BaseModel):
    default: str
    providers: list[ProviderOut]


class IndexStatus(BaseModel):
    ready: bool
    documents: int | None = None
    chunks: int | None = None
    embedding_model: str | None = None
    error: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
