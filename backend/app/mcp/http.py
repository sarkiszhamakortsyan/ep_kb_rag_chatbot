"""Serves the MCP server over Streamable HTTP inside the API at /api/mcp/, behind MCP_TOKEN."""

import json
import secrets
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

MOUNT_PATH = "/api/mcp"


class BearerTokenGuard:
    """Rejects requests without `Authorization: Bearer <MCP_TOKEN>` (constant-time check)."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self._authorized(scope):
            body = json.dumps(
                {"error": {"code": "unauthorized", "message": "Missing or invalid MCP token."}}
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        headers: dict[bytes, bytes] = dict(scope.get("headers", []))
        scheme, _, token = headers.get(b"authorization", b"").partition(b" ")
        return scheme.lower() == b"bearer" and secrets.compare_digest(token, self._token)


def mcp_http_app(server: MCPServer, token: str, allowed_hosts: list[str]) -> Any:
    """The ASGI app to mount at MOUNT_PATH. Its session manager must run in the API lifespan."""
    hosts = [pattern for host in allowed_hosts for pattern in (host, f"{host}:*")]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[f"{scheme}://{host}" for host in hosts for scheme in ("http", "https")],
    )
    # Stateless: every request stands alone, so no session state lives in the API process.
    app = server.streamable_http_app(
        streamable_http_path="/", stateless_http=True, transport_security=security
    )
    return BearerTokenGuard(app, token)
