from pathlib import Path

import pytest

from app.rag.models import Chunk
from app.stores.vector.memory import InMemoryVectorStore


def chunk(n: int) -> Chunk:
    return Chunk(f"d#{n:03d}", "d", "Doc", f"S{n}", f"text {n}")


@pytest.fixture
def store() -> InMemoryVectorStore:
    s = InMemoryVectorStore()
    s.add([chunk(0), chunk(1), chunk(2)], [[1, 0, 0], [0.7, 0.7, 0], [0, 0, 5]])
    return s


def test_search_orders_by_cosine_similarity(store: InMemoryVectorStore) -> None:
    results = store.search([1, 0.1, 0], k=3)
    assert [r.chunk.chunk_id for r in results] == ["d#000", "d#001", "d#002"]
    assert results[0].score == pytest.approx(0.995, abs=1e-3)
    assert results[2].score == pytest.approx(0.0, abs=1e-6)


def test_vector_length_does_not_matter(store: InMemoryVectorStore) -> None:
    assert store.search([0, 0, 0.001], k=1)[0].score == pytest.approx(1.0)


def test_k_larger_than_store(store: InMemoryVectorStore) -> None:
    assert len(store.search([1, 0, 0], k=10)) == 3


def test_empty_store_and_zero_k() -> None:
    assert InMemoryVectorStore().search([1, 0], k=3) == []
    assert InMemoryVectorStore().count() == 0


def test_add_appends(store: InMemoryVectorStore) -> None:
    store.add([chunk(3)], [[0, 1, 0]])
    assert store.count() == 4
    assert store.search([0, 1, 0], k=1)[0].chunk.chunk_id == "d#003"


def test_mismatched_inputs_are_rejected(store: InMemoryVectorStore) -> None:
    with pytest.raises(ValueError, match="chunks but"):
        store.add([chunk(5)], [])
    with pytest.raises(ValueError, match="dimension"):
        store.add([chunk(5)], [[1, 0]])
    with pytest.raises(ValueError, match="dimension"):
        store.search([1, 0], k=1)


def test_save_and_load_round_trip(store: InMemoryVectorStore, tmp_path: Path) -> None:
    store.save(tmp_path)
    loaded = InMemoryVectorStore.load(tmp_path)
    assert loaded.count() == 3
    assert loaded.search([0.7, 0.7, 0], k=1)[0].chunk == chunk(1)
