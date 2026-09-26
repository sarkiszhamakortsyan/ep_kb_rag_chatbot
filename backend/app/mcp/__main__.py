"""Runs the knowledge base as a local MCP server over stdio.

MCP clients (Claude Desktop, Claude Code, ...) start it as a subprocess, for example:

  claude mcp add omnicorp-kb -- uv run --directory /path/to/backend python -m app.mcp

It builds the same services as the API in-process, so Ollama must be reachable for the
embeddings (OLLAMA_BASE_URL) and ANTHROPIC_API_KEY is needed for Claude answers.
"""

import asyncio
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.mcp.server import build_mcp_server
from app.services import create_services


async def serve() -> None:
    settings = get_settings()
    services = await create_services(settings)
    try:
        await build_mcp_server(lambda: services).run_stdio_async()
    finally:
        await services.aclose()


if __name__ == "__main__":
    configure_logging(get_settings().log_level, stream=sys.stderr)
    asyncio.run(serve())
