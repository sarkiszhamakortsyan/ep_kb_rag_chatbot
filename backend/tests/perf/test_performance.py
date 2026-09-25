"""Speed and performance tests (offline). Run: uv run pytest -m perf -s

Thresholds are generous so they hold on a slow CI runner; the printed numbers are the
actual measurements (recorded in documentation/evaluation.md).
"""

import asyncio
import statistics
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import numpy as np
import pytest

from app.core.config import Settings
from app.evaluation.stats import percentile
from app.main import create_app
from app.rag.chunking import chunk_document
from app.rag.ingest import build_or_load_index, load_documents
from app.rag.models import Chunk
from app.services import Services, create_services
from app.stores.vector.memory import InMemoryVectorStore
from tests.fakes import FakeEmbedder, FakeLLM

pytestmark = pytest.mark.perf

KB_DIR = Path("data/kb")


def timed_ms(fn: Callable[[], object], repeat: int) -> list[float]:
    samples = []
    for _ in range(repeat):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


@pytest.mark.parametrize("chunks", [1_000, 50_000])
def test_vector_search_scales(chunks: int) -> None:
    rng = np.random.default_rng(0)
    store = InMemoryVectorStore()
    vectors = rng.standard_normal((chunks, 768)).astype(np.float32)
    store.add([Chunk(f"c{i}", "d", "T", "S", "t") for i in range(chunks)], vectors.tolist())
    query = rng.standard_normal(768).tolist()

    samples = timed_ms(lambda: store.search(query, k=6), repeat=50)
    p95 = percentile(samples, 95)
    p50 = statistics.median(samples)
    print(f"\nvector search, {chunks:,} chunks x 768 dims: p50 {p50:.2f} ms, p95 {p95:.2f} ms")
    assert p95 is not None and p95 < (20 if chunks <= 1_000 else 250)


def test_chunking_the_kb_is_fast() -> None:
    documents = load_documents(KB_DIR)
    samples = timed_ms(lambda: [chunk_document(d) for d in documents], repeat=20)
    print(f"\nchunking 5 articles: p50 {statistics.median(samples):.2f} ms")
    assert statistics.median(samples) < 200


@pytest.mark.anyio
async def test_cached_index_loads_fast(tmp_path: Path) -> None:
    embedder = FakeEmbedder(dimensions=768)
    await build_or_load_index(KB_DIR, tmp_path, embedder)  # build once
    started = time.perf_counter()
    _, report = await build_or_load_index(KB_DIR, tmp_path, embedder)
    elapsed = (time.perf_counter() - started) * 1000
    print(f"\ncached index load ({report.chunks} chunks): {elapsed:.1f} ms")
    assert not report.rebuilt and elapsed < 500


@pytest.mark.anyio
async def test_api_overhead_under_concurrency(tmp_path: Path) -> None:
    """End-to-end API cost excluding the model: fake LLM/embedder, 200 requests, 20 at a time."""
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        kb_dir=KB_DIR,
        index_dir=tmp_path,
        min_score=0.0,
        enabled_llm_providers=["ollama"],
        llm_provider="ollama",
    )

    async def factory(s: Settings) -> Services:
        return await create_services(
            s,
            llm_factories={"ollama": lambda _: FakeLLM("Backups are retained for 35 days [1].")},
            embedding_factories={"ollama": lambda _: FakeEmbedder(dimensions=768)},
        )

    app = create_app(settings, factory, load_in_background=False)
    latencies: list[float] = []
    semaphore = asyncio.Semaphore(20)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

            async def one(i: int) -> int:
                async with semaphore:
                    started = time.perf_counter()
                    response = await client.post(
                        "/api/v1/chat", json={"message": f"How long are backups kept? {i}"}
                    )
                    latencies.append((time.perf_counter() - started) * 1000)
                    return response.status_code

            started = time.perf_counter()
            statuses = await asyncio.gather(*(one(i) for i in range(200)))
            wall = time.perf_counter() - started

    p95 = percentile(latencies, 95)
    print(
        f"\nAPI (fake model), 200 requests @ concurrency 20: {200 / wall:.0f} req/s, "
        f"p50 {statistics.median(latencies):.1f} ms, p95 {p95:.1f} ms"
    )
    assert statuses == [200] * 200
    assert p95 is not None and p95 < 500
