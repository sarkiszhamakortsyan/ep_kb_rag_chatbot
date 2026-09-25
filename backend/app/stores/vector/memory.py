import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

import numpy as np
import numpy.typing as npt

from app.rag.models import Chunk
from app.stores.vector.base import SearchResult, VectorStore

VECTORS_FILE = "vectors.npy"
CHUNKS_FILE = "chunks.json"


class InMemoryVectorStore(VectorStore):
    """Exact cosine-similarity search over an L2-normalised numpy matrix.

    Brute force is exact and takes microseconds at prototype scale (~100 chunks);
    it stays practical up to roughly 100k chunks.
    """

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._matrix: npt.NDArray[np.float32] | None = None

    def add(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if not chunks:
            return
        matrix = _normalise(np.asarray(vectors, dtype=np.float32))
        if self._matrix is not None and matrix.shape[1] != self._matrix.shape[1]:
            raise ValueError(
                f"Vector dimension {matrix.shape[1]} does not match store {self._matrix.shape[1]}"
            )
        self._matrix = matrix if self._matrix is None else np.vstack([self._matrix, matrix])
        self._chunks.extend(chunks)

    def search(self, vector: Sequence[float], k: int) -> list[SearchResult]:
        if self._matrix is None or k <= 0:
            return []
        query = _normalise(np.asarray([vector], dtype=np.float32))
        if query.shape[1] != self._matrix.shape[1]:
            raise ValueError(
                f"Query dimension {query.shape[1]} does not match store {self._matrix.shape[1]}"
            )
        scores = self._matrix @ query[0]
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top], kind="stable")]
        return [SearchResult(self._chunks[i], float(scores[i])) for i in top]

    def count(self) -> int:
        return len(self._chunks)

    # --- persistence (the on-disk index cache) ---------------------------------

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        matrix = self._matrix if self._matrix is not None else np.zeros((0, 0), np.float32)
        np.save(directory / VECTORS_FILE, matrix)
        (directory / CHUNKS_FILE).write_text(
            json.dumps([asdict(c) for c in self._chunks], ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, directory: Path) -> "InMemoryVectorStore":
        store = cls()
        chunks = [
            Chunk(**c) for c in json.loads((directory / CHUNKS_FILE).read_text(encoding="utf-8"))
        ]
        matrix = np.load(directory / VECTORS_FILE)
        if len(chunks) != len(matrix):
            raise ValueError("Index cache is inconsistent: chunk and vector counts differ")
        if chunks:
            store._chunks = chunks
            store._matrix = matrix.astype(np.float32)
        return store


def _normalise(matrix: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return (matrix / np.where(norms == 0, 1.0, norms)).astype(np.float32)
