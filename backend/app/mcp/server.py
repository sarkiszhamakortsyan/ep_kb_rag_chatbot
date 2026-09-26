"""MCP tools and resources over the same services as the web API.

- `search_knowledge_base` returns the best-matching sections; the calling assistant writes its
  own answer from them.
- `ask_knowledge_base` runs the full pipeline, so answers keep this project's rules: sources
  only, citations, and a refusal when the documentation has no answer.
- `kb://documents` lists the articles and `kb://documents/{doc_id}` returns one in full.
"""

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError

from app.providers.errors import ProviderError
from app.rag.ingest import load_documents
from app.rag.pipeline import ChatOptions
from app.rag.prompts import LANGUAGES
from app.services import Services

INSTRUCTIONS = (
    "OmniCorp's internal knowledge base for Customer Success Managers: SSO and user "
    "provisioning, API rate limits, data retention and GDPR, webhooks and integrations, "
    "support tiers and SLAs. Use ask_knowledge_base for a cited answer, or "
    "search_knowledge_base to read the relevant sections yourself. Only state what the "
    "returned sources say."
)


def build_mcp_server(get_services: Callable[[], Services]) -> MCPServer:
    """`get_services` returns the ready services or raises (e.g. while the index is loading)."""
    server = MCPServer("omnicorp-knowledge-base", instructions=INSTRUCTIONS)

    def services() -> Services:
        try:
            return get_services()
        except Exception as exc:  # e.g. ServiceNotReadyError: tell the client why
            raise ToolError(str(exc)) from exc

    @server.tool()
    async def search_knowledge_base(query: str, k: int = 6) -> list[dict[str, Any]]:
        """Find the knowledge-base sections most similar to a query, best first.

        Each result has the document id and title, the section heading path, the section text
        and a cosine similarity score (0.55 or more is a strong match)."""
        result = await services().retriever.retrieve(query, top_k=max(1, min(k, 20)))
        return [
            {
                "doc_id": r.chunk.doc_id,
                "title": r.chunk.title,
                "section": r.chunk.section,
                "text": r.chunk.text,
                "score": round(r.score, 3),
            }
            for r in result.results
        ]

    @server.tool()
    async def ask_knowledge_base(
        question: str, model: str | None = None, language: str | None = None
    ) -> dict[str, Any]:
        """Answer a question strictly from the knowledge base, with numbered citations.

        `model` picks the provider ("anthropic" or "ollama"; default: the server's default).
        `language` is an ISO code (en, de, fr, es, it, pt, nl, pl) to fix the answer language.
        When the documentation does not cover the question, `refused` is true."""
        if language is not None and language not in LANGUAGES:
            raise ToolError(f"Unsupported language; use one of {', '.join(LANGUAGES)}")
        try:
            result = await services().pipeline.answer(
                question, options=ChatOptions(provider=model, language=language)
            )
        except ProviderError as exc:  # unknown/disabled model, provider down: say which
            raise ToolError(str(exc)) from exc
        return {
            "answer": result.answer,
            "refused": result.refused,
            "citations": [
                {"number": c.number, "doc_id": c.doc_id, "title": c.title, "section": c.section}
                for c in result.citations
            ],
            "model": result.model,
        }

    @server.resource("kb://documents", mime_type="application/json")
    def list_articles() -> list[dict[str, str]]:
        """All knowledge-base articles (id and title)."""
        docs = load_documents(services().settings.kb_dir)
        return [
            {"doc_id": d.doc_id, "title": d.title, "uri": f"kb://documents/{d.doc_id}"}
            for d in docs
        ]

    @server.resource("kb://documents/{doc_id}", mime_type="text/markdown")
    def read_article(doc_id: str) -> str:
        """One knowledge-base article in full (Markdown)."""
        for doc in load_documents(services().settings.kb_dir):
            if doc.doc_id == doc_id:
                return f"# {doc.title}\n\n{doc.body}"
        raise ResourceNotFoundError(f"No article {doc_id!r}")

    return server
