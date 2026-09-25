import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.providers.errors import ProviderError, ProviderUnavailableError
from app.providers.llm.base import (
    ChatMessage,
    GenerationDone,
    GenerationOptions,
    LLMProvider,
    StreamEvent,
    TextDelta,
    Usage,
)

_DEFAULT_MAX_OUTPUT_TOKENS = 1024


class OllamaLLMProvider(LLMProvider):
    """Streams chat completions from Ollama's `/api/chat` (newline-delimited JSON)."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        num_ctx: int = 4096,
        keep_alive: str = "30m",
        think: bool | None = None,
        timeout_s: float = 300.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._num_ctx = num_ctx
        self._keep_alive = keep_alive
        # Only sent when set: models without a thinking mode reject the parameter.
        self._think = think
        # The read timeout covers prompt processing before the first token, which can take
        # minutes for a RAG prompt on a slow CPU.
        self._timeout_s = timeout_s
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(connect=5.0, read=timeout_s, write=30.0, pool=5.0),
        )

    def _payload(
        self, system: str, messages: Sequence[ChatMessage], options: GenerationOptions
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": options.temperature,
                "num_ctx": self._num_ctx,
                "num_predict": options.max_output_tokens or _DEFAULT_MAX_OUTPUT_TOKENS,
            },
        }
        if self._think is not None:
            payload["think"] = self._think
        return payload

    async def stream(
        self,
        system: str,
        messages: Sequence[ChatMessage],
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        payload = self._payload(system, messages, options or GenerationOptions())
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise _status_error(response)
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise ProviderError(f"Ollama error: {chunk['error']}")
                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        yield TextDelta(text)
                    if chunk.get("done"):
                        yield GenerationDone(
                            usage=Usage(
                                input_tokens=chunk.get("prompt_eval_count", 0),
                                output_tokens=chunk.get("eval_count", 0),
                            ),
                            stop_reason=_stop_reason(chunk.get("done_reason")),
                            model=self.model,
                        )
                        return
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                f"Ollama did not respond within {self._timeout_s:.0f} s (model too slow for this "
                "hardware? raise OLLAMA_TIMEOUT_S or use a smaller model)"
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(f"Ollama is unreachable: {exc!r}") from exc
        raise ProviderUnavailableError("Ollama closed the stream before finishing")

    async def aclose(self) -> None:
        await self._client.aclose()


def _stop_reason(done_reason: str | None) -> str | None:
    return {"stop": "end_turn", "length": "max_tokens"}.get(done_reason or "", done_reason)


def _status_error(response: httpx.Response) -> ProviderError:
    try:
        detail = response.json().get("error", response.text)
    except ValueError:
        detail = response.text
    message = f"Ollama returned HTTP {response.status_code}: {detail}"
    if response.status_code >= 500:
        return ProviderUnavailableError(message)
    return ProviderError(message)
