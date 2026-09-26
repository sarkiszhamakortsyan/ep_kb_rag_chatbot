"""In-process embeddings with fastembed (ONNX Runtime, no PyTorch), for running without Ollama.

The default model is `google/embeddinggemma-300m`, the same model Ollama serves, so the vectors
are identical (cosine 1.000 in our comparison) and all thresholds stay valid. On first use the
model files (about 1.2 GB) are downloaded from Hugging Face into `models_dir`, a Docker volume.
They are saved as plain files: ONNX Runtime refuses the symlinked layout of the Hugging Face
cache for models with external weight files.
"""

import asyncio
import logging
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.providers.embeddings.base import EmbeddingDocument, EmbeddingProvider, Vector
from app.providers.embeddings.prompts import prompts_for
from app.providers.errors import ProviderConfigError, ProviderUnavailableError

logger = logging.getLogger(__name__)

_CONFIG_FILES = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
]


class LocalEmbeddingProvider(EmbeddingProvider):
    name = "local"

    def __init__(self, model: str, models_dir: Path, *, batch_size: int = 16) -> None:
        self.model = model
        self._models_dir = models_dir
        self._batch_size = batch_size
        self._query_prompt, self._document_prompt = prompts_for(model)
        self.document_format = self._document_prompt
        self._engine: Any = None
        self._lock = threading.Lock()

    async def embed_documents(self, documents: Sequence[EmbeddingDocument]) -> list[Vector]:
        texts = [
            self._document_prompt.format(title=d.title or "none", text=d.text) for d in documents
        ]
        return await asyncio.to_thread(self._embed, texts)

    async def embed_query(self, query: str) -> Vector:
        return (await asyncio.to_thread(self._embed, [self._query_prompt.format(text=query)]))[0]

    def _embed(self, texts: list[str]) -> list[Vector]:
        engine = self._load()
        return [vector.tolist() for vector in engine.embed(texts, batch_size=self._batch_size)]

    def _load(self) -> Any:
        with self._lock:  # one download/load, even with concurrent first requests
            if self._engine is None:
                self._engine = self._create_engine()
            return self._engine

    def _create_engine(self) -> Any:
        from fastembed import TextEmbedding

        info = next(
            (m for m in TextEmbedding.list_supported_models() if m["model"] == self.model), None
        )
        if info is None:
            raise ProviderConfigError(f"fastembed does not support the model {self.model!r}")
        target = self._models_dir / self.model.replace("/", "--")
        if not (target / info["model_file"]).exists():
            self._download(info, target)
        logger.info("Loading embedding model %s from %s", self.model, target)
        return TextEmbedding(self.model, specific_model_path=str(target))

    def _download(self, info: dict[str, Any], target: Path) -> None:
        from huggingface_hub import snapshot_download

        repo = info["sources"]["hf"]
        files = [*_CONFIG_FILES, info["model_file"], *info.get("additional_files", [])]
        logger.info("Downloading embedding model %s (%s) to %s", self.model, repo, target)
        try:
            snapshot_download(repo_id=repo, local_dir=target, allow_patterns=files)
        except Exception as exc:  # network errors: retried by the startup loader
            raise ProviderUnavailableError(f"Could not download {repo}: {exc}") from exc
