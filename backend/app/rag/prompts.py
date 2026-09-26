"""Prompt templates live in app/prompts/*.md so they can be reviewed and versioned like code.
Optional sections are appended for a detailed answer (ideas.md #3) or a fixed answer language
(ideas.md #4); without options the system prompt is exactly `system.md`."""

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from app.stores.vector.base import SearchResult

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


# Answer languages offered in the UI (ISO 639-1 code -> the name used in the prompt).
LANGUAGES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
}


@lru_cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def system_prompt(detail: str = "concise", language: str | None = None) -> str:
    """The system prompt plus the sections for the requested answer style."""
    parts = [load_prompt("system")]
    if detail == "detailed":
        parts.append(load_prompt("detail_detailed"))
    if language:
        parts.append(load_prompt("answer_language").format(language=LANGUAGES[language]))
    return "\n\n".join(parts)


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
