import json
import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.providers.embeddings.base import EmbeddingDocument, Vector
from app.rag.chunking import ChunkingConfig
from app.rag.ingest import MANIFEST_FILE, build_or_load_index, load_documents
from app.rag.retrieval import Retriever
from tests.fakes import FakeEmbedder

pytestmark = pytest.mark.anyio


class CountingEmbedder(FakeEmbedder):
    def __init__(self, model: str = "fake-embed") -> None:
        super().__init__(model=model)
        self.documents_embedded = 0

    async def embed_documents(self, documents: Sequence[EmbeddingDocument]) -> list[Vector]:
        self.documents_embedded += len(documents)
        return await super().embed_documents(documents)


def write_doc(kb: Path, doc_id: str, body: str) -> None:
    (kb / f"{doc_id}.md").write_text(
        f"---\nid: {doc_id}\ntitle: {doc_id} title\n---\n# T\n\n{body}\n", encoding="utf-8"
    )


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir()
    write_doc(kb, "kb-1", "## Backups\n\nBackups are retained for 35 days.")
    write_doc(kb, "kb-2", "## Webhooks\n\nWebhooks are signed with HMAC.")
    return kb


async def test_builds_index_then_reuses_cache(kb: Path, tmp_path: Path) -> None:
    index = tmp_path / "index"
    embedder = CountingEmbedder()

    store, report = await build_or_load_index(kb, index, embedder)
    assert report.rebuilt and report.documents == 2 and report.chunks == 2
    assert embedder.documents_embedded == 2
    manifest = json.loads((index / MANIFEST_FILE).read_text())
    assert manifest["fingerprint"] == report.fingerprint

    cached, report2 = await build_or_load_index(kb, index, embedder)
    assert not report2.rebuilt
    assert embedder.documents_embedded == 2  # nothing re-embedded
    assert cached.count() == store.count()


async def test_changed_document_triggers_rebuild(kb: Path, tmp_path: Path) -> None:
    index = tmp_path / "index"
    _, first = await build_or_load_index(kb, index, CountingEmbedder())
    write_doc(kb, "kb-2", "## Webhooks\n\nWebhooks are signed with HMAC-SHA256.")
    _, second = await build_or_load_index(kb, index, CountingEmbedder())
    assert second.rebuilt and second.fingerprint != first.fingerprint


async def test_changed_model_or_chunking_triggers_rebuild(kb: Path, tmp_path: Path) -> None:
    index = tmp_path / "index"
    await build_or_load_index(kb, index, CountingEmbedder())
    _, other_model = await build_or_load_index(kb, index, CountingEmbedder(model="other"))
    assert other_model.rebuilt
    _, other_chunking = await build_or_load_index(
        kb, index, CountingEmbedder(model="other"), ChunkingConfig(max_words=100)
    )
    assert other_chunking.rebuilt


async def test_changed_document_prompt_triggers_rebuild(kb: Path, tmp_path: Path) -> None:
    index = tmp_path / "index"
    await build_or_load_index(kb, index, CountingEmbedder())
    embedder = CountingEmbedder()
    embedder.document_format = "title: {title} | text: {text}"
    _, report = await build_or_load_index(kb, index, embedder)
    assert report.rebuilt and embedder.documents_embedded == 2


async def test_corrupt_cache_is_rebuilt(kb: Path, tmp_path: Path) -> None:
    index = tmp_path / "index"
    await build_or_load_index(kb, index, CountingEmbedder())
    (index / "chunks.json").write_text("not json")
    _, report = await build_or_load_index(kb, index, CountingEmbedder())
    assert report.rebuilt


async def test_force_rebuilds(kb: Path, tmp_path: Path) -> None:
    index = tmp_path / "index"
    await build_or_load_index(kb, index, CountingEmbedder())
    _, report = await build_or_load_index(kb, index, CountingEmbedder(), force=True)
    assert report.rebuilt


async def test_index_is_written_within_the_index_dir(
    kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # In Docker the index dir is a mounted volume: renames from outside it fail (EXDEV).
    index = tmp_path / "index"
    moves: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def recording_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        moves.append((Path(src), Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", recording_replace)
    await build_or_load_index(kb, index, CountingEmbedder())
    assert moves and all(index in src.parents and dst.parent == index for src, dst in moves)
    assert moves[-1][1].name == MANIFEST_FILE  # manifest published last
    assert sorted(p.name for p in index.iterdir()) == ["chunks.json", MANIFEST_FILE, "vectors.npy"]


def test_duplicate_ids_are_rejected(kb: Path) -> None:
    (kb / "copy.md").write_text((kb / "kb-1.md").read_text())
    with pytest.raises(ValueError, match="Duplicate document id 'kb-1'"):
        load_documents(kb)


def test_empty_kb_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_documents(tmp_path)


async def test_retriever_ranks_and_applies_min_score(kb: Path, tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    store, _ = await build_or_load_index(kb, tmp_path / "index", embedder)
    retriever = Retriever(embedder, store, top_k=2, min_score=0.3)

    hit = await retriever.retrieve("How long are backups retained?")
    assert hit.results[0].chunk.doc_id == "kb-1"
    assert hit.covered and hit.top_score == hit.results[0].score

    miss = await retriever.retrieve("zebra quantum")
    assert not miss.covered
