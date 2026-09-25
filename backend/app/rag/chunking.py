"""Structure-aware chunking: split on Markdown headings first, then pack blocks into windows.

Sizes are measured in words (1 word ≈ 1.3 tokens for English), so the default window of
300 words is about 400 tokens, with about 45 words (~60 tokens) of overlap between windows.
"""

import re
from dataclasses import dataclass

import yaml

from app.rag.models import Chunk, Document

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SECTION_SEPARATOR = " \u203a "  # single right-pointing angle quote: breadcrumb shown in citations


@dataclass(frozen=True)
class ChunkingConfig:
    max_words: int = 300
    overlap_words: int = 45

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_words < self.max_words:
            raise ValueError("overlap_words must be >= 0 and smaller than max_words")


def parse_document(markdown: str, source: str = "") -> Document:
    """Parse a KB article with YAML front matter (`id` and `title` are required)."""
    match = _FRONT_MATTER.match(markdown)
    if not match:
        raise ValueError(f"{source or 'document'}: missing YAML front matter")
    meta = yaml.safe_load(match.group(1)) or {}
    for key in ("id", "title"):
        if not meta.get(key):
            raise ValueError(f"{source or 'document'}: front matter is missing {key!r}")
    return Document(
        doc_id=str(meta["id"]),
        title=str(meta["title"]),
        body=markdown[match.end() :],
        lang=str(meta.get("lang", "en")),
        source=source,
        metadata=meta,
    )


def chunk_document(doc: Document, config: ChunkingConfig | None = None) -> list[Chunk]:
    config = config or ChunkingConfig()
    chunks: list[Chunk] = []
    for path, blocks in _sections(doc.body):
        section = SECTION_SEPARATOR.join(path)
        for text in _pack(blocks, config):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#{len(chunks):03d}",
                    doc_id=doc.doc_id,
                    title=doc.title,
                    section=section,
                    text=text,
                    lang=doc.lang,
                )
            )
    return chunks


def _sections(body: str) -> list[tuple[list[str], list[str]]]:
    """Return (heading path, blocks) per section. The H1 title is not part of the path."""
    sections: list[tuple[list[str], list[str]]] = []
    stack: list[tuple[int, str]] = []
    lines: list[str] = []

    def flush() -> None:
        blocks = _blocks("\n".join(lines))
        if blocks:
            sections.append(([title for level, title in stack if level > 1], blocks))
        lines.clear()

    for line in body.splitlines():
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            stack = [(lvl, t) for lvl, t in stack if lvl < level] + [(level, heading.group(2))]
        else:
            lines.append(line)
    flush()
    return sections


def _blocks(text: str) -> list[str]:
    """Paragraphs, lists and tables separated by blank lines, kept intact."""
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


def _words(text: str) -> int:
    return len(text.split())


def _pack(blocks: list[str], config: ChunkingConfig) -> list[str]:
    """Greedily pack blocks into windows of at most `max_words`, overlapping by whole blocks."""
    pieces: list[str] = []
    for block in blocks:
        pieces.extend(_split_long(block, config) if _words(block) > config.max_words else [block])

    windows: list[str] = []
    current: list[str] = []
    for piece in pieces:
        if current and _words("\n\n".join([*current, piece])) > config.max_words:
            windows.append("\n\n".join(current))
            current = _overlap_tail(current, config.overlap_words)
            # Drop the overlap if it would still overflow together with the next piece.
            if _words("\n\n".join([*current, piece])) > config.max_words:
                current = []
        current.append(piece)
    if current:
        windows.append("\n\n".join(current))
    return windows


def _overlap_tail(blocks: list[str], overlap_words: int) -> list[str]:
    tail: list[str] = []
    for block in reversed(blocks):
        if _words("\n\n".join([block, *tail])) > overlap_words:
            break
        tail.insert(0, block)
    return tail


def _split_long(block: str, config: ChunkingConfig) -> list[str]:
    """Split an oversized block by words, with `overlap_words` of overlap."""
    words = block.split()
    step = config.max_words - config.overlap_words
    return [
        " ".join(words[start : start + config.max_words])
        for start in range(0, max(len(words) - config.overlap_words, 1), step)
    ]
