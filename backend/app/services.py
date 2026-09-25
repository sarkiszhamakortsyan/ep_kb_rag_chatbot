"""Builds the object graph (providers, index, pipeline) from settings. Used by the API
startup and the CLIs, so all entry points are wired the same way."""

from dataclasses import dataclass

from app.core.config import Settings
from app.providers.embeddings.registry import EmbeddingRegistry, build_embedding_registry
from app.providers.llm.registry import LLMRegistry, build_llm_registry
from app.rag.ingest import IndexReport, build_or_load_index
from app.rag.pipeline import RagPipeline
from app.rag.retrieval import Retriever
from app.stores.events.base import EventStore
from app.stores.events.log_only import LogOnlyEventStore


@dataclass
class Services:
    settings: Settings
    llms: LLMRegistry
    embeddings: EmbeddingRegistry
    index: IndexReport
    retriever: Retriever
    pipeline: RagPipeline

    async def aclose(self) -> None:
        await self.llms.aclose()
        await self.embeddings.aclose()


async def create_services(settings: Settings, events: EventStore | None = None) -> Services:
    embeddings = build_embedding_registry(settings)
    llms = build_llm_registry(settings)
    try:
        embedder = embeddings.get()
        store, report = await build_or_load_index(
            settings.kb_dir, settings.index_dir, embedder, settings.chunking()
        )
    except BaseException:
        await embeddings.aclose()
        raise
    retriever = Retriever(embedder, store, top_k=settings.top_k, min_score=settings.min_score)
    pipeline = RagPipeline(retriever, llms, events or LogOnlyEventStore())
    return Services(settings, llms, embeddings, report, retriever, pipeline)
