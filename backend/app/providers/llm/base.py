"""Chat-model provider interface.

Providers stream text and finish with a `GenerationDone` event that carries token usage,
so the pipeline can report latency and cost (ideas.md #1, #2) without provider-specific code.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class GenerationOptions:
    # Ignored by models that reject sampling parameters (Claude Opus 5 / Sonnet 5).
    temperature: float = 0.1
    # None = the provider's own default.
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class GenerationDone:
    usage: Usage
    # Normalised: "end_turn" | "max_tokens" | "refusal" | other provider-specific values.
    stop_reason: str | None = None
    # The model that actually produced the answer (can differ after a server-side fallback).
    model: str | None = None


StreamEvent = TextDelta | GenerationDone


@dataclass
class Generation:
    text: str
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None
    model: str | None = None


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def stream(
        self,
        system: str,
        messages: Sequence[ChatMessage],
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield `TextDelta`s, then exactly one final `GenerationDone`."""

    async def generate(
        self,
        system: str,
        messages: Sequence[ChatMessage],
        options: GenerationOptions | None = None,
    ) -> Generation:
        """Non-streaming convenience wrapper around `stream`."""
        parts: list[str] = []
        result = Generation(text="")
        async for event in self.stream(system, messages, options):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            else:
                result = Generation(
                    text="", usage=event.usage, stop_reason=event.stop_reason, model=event.model
                )
        result.text = "".join(parts)
        return result

    async def aclose(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Release network resources."""
