"""MCP tools and resources over the same services as the web API.

- `search_knowledge_base` returns the best-matching sections; the calling assistant writes its
  own answer from them.
- `ask_knowledge_base` runs the full pipeline, so answers keep this project's rules: sources
  only, citations, and a refusal when the documentation has no answer.
- `kb://documents` lists the articles and `kb://documents/{doc_id}` returns one in full.
- The prompts `ask`, `ask_claude` and `ask_local` turn a question into a request to use
  `ask_knowledge_base`, so clients can offer them as commands (e.g. `/mcp__omnicorp-kb__ask`).

`model` accepts the names used in the web chat and the CLI as well: `claude`, `local`, the
model family (`ministral`) or the full model id (`ministral-3:3b`).
"""

import re
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError

from app.cli.models import SHORT_NAMES
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


PROMPT = (
    "Answer this question with the omnicorp-kb tool ask_knowledge_base{model}. Show its answer "
    "with the numbered citations (document and section). If it returns refused: true, say "
    "that the knowledge base doesn't cover the question; don't answer from general knowledge."
    "\n\nQuestion: {question}"
)


def resolve_model(requested: str | None, services: Services) -> str | None:
    """The provider name for a model name typed by a person or picked by the client.

    Accepts the provider (`ollama`), the short name (`local`, `claude`), the model family
    (`ministral`) or the full model id (`ministral-3:3b`), in any case, with or without `/`."""
    if requested is None or not requested.strip():
        return None
    wanted = requested.strip().lstrip("/").lower()
    names: dict[str, str] = {}
    for provider in services.llms.enabled:
        names[provider] = provider
        if provider in SHORT_NAMES:
            names.setdefault(SHORT_NAMES[provider], provider)
        try:
            model = (services.llms.get(provider).model or "").lower()
        except ProviderError:
            continue  # e.g. no API key: the provider name still works and explains why
        if model:
            names.setdefault(model, provider)
            names.setdefault(re.split(r"[-:]", model)[0], provider)
    for provider, short in SHORT_NAMES.items():  # disabled ones too, for a clear error
        names.setdefault(provider, provider)
        names.setdefault(short, provider)
    if wanted in names:
        return names[wanted]
    raise ToolError(f"Unknown model {requested!r}; use one of: {', '.join(sorted(names))}")


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

        `model` picks the model: "anthropic"/"claude", "ollama"/"local", a model family such as
        "ministral", or a full model id such as "ministral-3:3b" (default: the server's default).
        `language` is an ISO code (en, de, fr, es, it, pt, nl, pl) to fix the answer language.
        When the documentation does not cover the question, `refused` is true."""
        if language is not None and language not in LANGUAGES:
            raise ToolError(f"Unsupported language; use one of {', '.join(LANGUAGES)}")
        try:
            ready = services()
            result = await ready.pipeline.answer(
                question,
                options=ChatOptions(provider=resolve_model(model, ready), language=language),
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

    @server.prompt(title="Ask the knowledge base")
    def ask(question: str) -> str:
        """Ask the OmniCorp knowledge base with the default model; the answer has citations."""
        return PROMPT.format(model="", question=question)

    @server.prompt(title="Ask the knowledge base (Claude)")
    def ask_claude(question: str) -> str:
        """Ask the OmniCorp knowledge base and have Claude write the answer."""
        return PROMPT.format(model=' with model "anthropic"', question=question)

    @server.prompt(title="Ask the knowledge base (local model)")
    def ask_local(question: str) -> str:
        """Ask the OmniCorp knowledge base and have the local Ollama model write the answer."""
        return PROMPT.format(model=' with model "ollama"', question=question)

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
