from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.providers.embeddings.base import EmbeddingDocument
from app.providers.embeddings.local import LocalEmbeddingProvider
from app.providers.errors import ProviderConfigError

pytestmark = pytest.mark.anyio


class FakeEngine:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: list[str], batch_size: int = 16) -> Any:
        self.texts.extend(texts)
        return (np.array([float(len(t)), 1.0]) for t in texts)


async def test_uses_the_same_task_prompts_as_ollama(tmp_path: Path) -> None:
    provider = LocalEmbeddingProvider("google/embeddinggemma-300m", tmp_path)
    engine = FakeEngine()
    provider._engine = engine  # skip the download

    vectors = await provider.embed_documents([EmbeddingDocument("Kept 35 days.", "Backups")])
    query = await provider.embed_query("How long?")

    assert engine.texts == [
        "title: Backups | text: Kept 35 days.",
        "task: search result | query: How long?",
    ]
    assert isinstance(vectors[0], list) and len(query) == 2


def test_unsupported_model_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ProviderConfigError):
        LocalEmbeddingProvider("no/such-model", tmp_path)._load()
