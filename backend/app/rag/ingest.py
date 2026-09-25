"""Load the KB, chunk it, embed it, and cache the index on disk.

The cache key (fingerprint) covers the document contents, the chunking parameters and the
embedding provider/model, so changing any of them triggers a clean rebuild on startup.

CLI: `uv run python -m app.rag.ingest [--force]`
"""

import asyncio
import hashlib
import json
import logging
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.providers.embeddings.base import EmbeddingDocument, EmbeddingProvider
from app.rag.chunking import ChunkingConfig, chunk_document, parse_document
from app.rag.models import Document
from app.stores.vector.memory import InMemoryVectorStore

logger = logging.getLogger(__name__)

MANIFEST_FILE = "manifest.json"
# Bump when the chunk/index format changes in a way the fingerprint cannot see.
INDEX_FORMAT_VERSION = 1


@dataclass(frozen=True)
class IndexReport:
    fingerprint: str
    embedding_model: str
    documents: int
    chunks: int
    rebuilt: bool
    duration_ms: float


def load_documents(kb_dir: Path) -> list[Document]:
    paths = sorted(kb_dir.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No Markdown documents found in {kb_dir}")
    documents = [parse_document(p.read_text(encoding="utf-8"), source=p.name) for p in paths]
    seen: dict[str, str] = {}
    for doc in documents:
        if doc.doc_id in seen:
            raise ValueError(
                f"Duplicate document id {doc.doc_id!r} in {seen[doc.doc_id]} and {doc.source}"
            )
        seen[doc.doc_id] = doc.source
    return documents


def fingerprint(
    documents: list[Document], config: ChunkingConfig, embedder: EmbeddingProvider
) -> str:
    digest = hashlib.sha256()
    digest.update(f"v{INDEX_FORMAT_VERSION}|{embedder.name}:{embedder.model}|".encode())
    digest.update(json.dumps(asdict(config), sort_keys=True).encode())
    for doc in sorted(documents, key=lambda d: d.doc_id):
        digest.update(f"|{doc.doc_id}|{doc.title}|{doc.lang}|".encode())
        digest.update(doc.body.encode())
    return digest.hexdigest()


async def build_or_load_index(
    kb_dir: Path,
    index_dir: Path,
    embedder: EmbeddingProvider,
    config: ChunkingConfig | None = None,
    *,
    force: bool = False,
) -> tuple[InMemoryVectorStore, IndexReport]:
    config = config or ChunkingConfig()
    started = time.perf_counter()
    documents = load_documents(kb_dir)
    key = fingerprint(documents, config, embedder)

    if not force:
        cached = _load_cached(index_dir, key)
        if cached is not None:
            return cached, _report(key, embedder, documents, cached, rebuilt=False, started=started)

    chunks = [chunk for doc in documents for chunk in chunk_document(doc, config)]
    vectors = await embedder.embed_documents(
        [EmbeddingDocument(text=c.embedding_text(), title=c.title) for c in chunks]
    )
    store = InMemoryVectorStore()
    store.add(chunks, vectors)
    _save(index_dir, store, key, embedder, len(documents))
    report = _report(key, embedder, documents, store, rebuilt=True, started=started)
    logger.info(
        "Built index: %d chunks from %d documents in %.0f ms",
        report.chunks,
        report.documents,
        report.duration_ms,
    )
    return store, report


def _load_cached(index_dir: Path, key: str) -> InMemoryVectorStore | None:
    manifest_path = index_dir / MANIFEST_FILE
    if not manifest_path.exists():
        return None
    try:
        if json.loads(manifest_path.read_text(encoding="utf-8")).get("fingerprint") != key:
            logger.info("Index cache is stale; rebuilding")
            return None
        return InMemoryVectorStore.load(index_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Index cache is unreadable (%s); rebuilding", exc)
        return None


def _save(
    index_dir: Path,
    store: InMemoryVectorStore,
    key: str,
    embedder: EmbeddingProvider,
    documents: int,
) -> None:
    # Write into a temporary directory and swap it in, so a crash never leaves a half-written
    # index that looks valid. The manifest is written last.
    tmp = index_dir.with_name(index_dir.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    store.save(tmp)
    manifest = {
        "fingerprint": key,
        "embedding_model": f"{embedder.name}:{embedder.model}",
        "documents": documents,
        "chunks": store.count(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (tmp / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    index_dir.mkdir(parents=True, exist_ok=True)
    # Replace the contents rather than the directory itself: in Docker it is a mounted volume.
    for item in index_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for item in tmp.iterdir():
        item.rename(index_dir / item.name)
    tmp.rmdir()


def _report(
    key: str,
    embedder: EmbeddingProvider,
    documents: list[Document],
    store: InMemoryVectorStore,
    *,
    rebuilt: bool,
    started: float,
) -> IndexReport:
    return IndexReport(
        fingerprint=key,
        embedding_model=f"{embedder.name}:{embedder.model}",
        documents=len(documents),
        chunks=store.count(),
        rebuilt=rebuilt,
        duration_ms=(time.perf_counter() - started) * 1000,
    )


async def _main(force: bool) -> None:
    from app.core.config import get_settings
    from app.providers.embeddings.registry import build_embedding_registry

    settings = get_settings()
    registry = build_embedding_registry(settings)
    try:
        _, report = await build_or_load_index(
            settings.kb_dir, settings.index_dir, registry.get(), settings.chunking(), force=force
        )
    finally:
        await registry.aclose()
    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main(force="--force" in sys.argv))
