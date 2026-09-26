"""Thin HTTP client for the public API, including the Server-Sent Events stream."""

import json
from collections.abc import Iterator
from typing import Any

import httpx


class ApiError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _raise_for(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        error = response.json()["error"]
        raise ApiError(error["code"], error["message"])
    except (ValueError, KeyError, TypeError):
        raise ApiError("http_error", f"HTTP {response.status_code}") from None


class KbClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self._http = client or httpx.Client(base_url=base_url, timeout=httpx.Timeout(900.0))
        self._prefix = "/api/v1"

    def get(self, path: str) -> Any:
        try:
            response = self._http.get(self._prefix + path)
        except httpx.TransportError as exc:
            raise ApiError("unreachable", f"Cannot reach the API: {exc}") from exc
        _raise_for(response)
        return response.json()

    def chat(self, body: dict[str, Any]) -> Any:
        try:
            response = self._http.post(self._prefix + "/chat", json=body)
        except httpx.TransportError as exc:
            raise ApiError("unreachable", f"Cannot reach the API: {exc}") from exc
        _raise_for(response)
        return response.json()

    def stream(self, body: dict[str, Any]) -> Iterator[tuple[str, Any]]:
        """Yields (event, data) pairs: meta, token..., then done or error."""
        try:
            with self._http.stream("POST", self._prefix + "/chat/stream", json=body) as response:
                if not response.is_success:
                    response.read()
                    _raise_for(response)
                event, data = "message", ""
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data += line[5:].strip()
                    elif not line and data:
                        yield event, _json(data)
                        event, data = "message", ""
                if data:
                    yield event, _json(data)
        except httpx.TransportError as exc:
            raise ApiError("unreachable", f"Cannot reach the API: {exc}") from exc

    def close(self) -> None:
        self._http.close()


def _json(text: str) -> Any:
    return json.loads(text)
