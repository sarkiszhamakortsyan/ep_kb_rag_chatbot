from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal

import anthropic

from app.providers.errors import ProviderConfigError, ProviderError, ProviderUnavailableError
from app.providers.llm.base import (
    ChatMessage,
    GenerationDone,
    GenerationOptions,
    LLMProvider,
    StreamEvent,
    TextDelta,
    Usage,
)

Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Streaming avoids HTTP timeouts, and adaptive thinking tokens count against this cap.
_DEFAULT_MAX_OUTPUT_TOKENS = 16000
# `fallbacks: "default"` lets the API re-run a safety-classifier refusal on the
# model Anthropic recommends for that refusal category.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLLMProvider(LLMProvider):
    """Streams answers from the Claude Messages API (bring-your-own API key).

    The system prompt carries a cache breakpoint: it is identical for every question,
    so repeated requests read it from the prompt cache (ideas.md #2, cost).
    `options.temperature` is not sent: current Claude models reject sampling parameters.
    """

    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        *,
        effort: Effort | None = None,
        refusal_fallback: bool = True,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if client is None and not api_key:
            raise ProviderConfigError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self._effort = effort
        self._refusal_fallback = refusal_fallback
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key)

    def _request(
        self, system: str, messages: Sequence[ChatMessage], options: GenerationOptions
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": options.max_output_tokens or _DEFAULT_MAX_OUTPUT_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if self._effort:
            request["output_config"] = {"effort": self._effort}
        if self._refusal_fallback:
            request["betas"] = [_FALLBACK_BETA]
            request["fallbacks"] = "default"
        return request

    async def stream(
        self,
        system: str,
        messages: Sequence[ChatMessage],
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        request = self._request(system, messages, options or GenerationOptions())
        try:
            async with self._client.beta.messages.stream(**request) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ProviderConfigError("Anthropic rejected the API key") from exc
        except anthropic.PermissionDeniedError as exc:
            raise ProviderConfigError(f"Anthropic denied access: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            message = f"Anthropic returned HTTP {exc.status_code}: {exc.message}"
            # 429 rate limit, 5xx server errors and 529 overloaded are worth retrying later.
            if exc.status_code == 429 or exc.status_code >= 500:
                raise ProviderUnavailableError(message) from exc
            raise ProviderError(message) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailableError(f"Anthropic is unreachable: {exc}") from exc

        usage = final.usage
        yield GenerationDone(
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=usage.cache_read_input_tokens or 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            ),
            stop_reason=final.stop_reason,
            model=final.model,
        )

    async def aclose(self) -> None:
        await self._client.close()
