"""Prompt templates live in app/prompts/*.md so they can be reviewed and versioned like code
(and later gain variants, e.g. a "detailed" answer style, ideas.md #3)."""

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from app.stores.vector.base import SearchResult

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def build_user_message(question: str, sources: Sequence[SearchResult]) -> str:
    """Numbered sources first, then the question. Numbers are 1-based positions in `sources`."""
    blocks = []
    for number, result in enumerate(sources, start=1):
        chunk = result.chunk
        header = f"Document: {chunk.title}"
        if chunk.section:
            header += f"\nSection: {chunk.section}"
        blocks.append(f'<source id="{number}">\n{header}\n\n{chunk.text}\n</source>')
    return "<sources>\n" + "\n".join(blocks) + f"\n</sources>\n\nQuestion: {question.strip()}"
