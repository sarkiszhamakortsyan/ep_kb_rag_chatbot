import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.stores.vector.base import SearchResult

# Matches [1], [2, 3] and [1][3] (each bracket separately).
_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass(frozen=True)
class Citation:
    number: int  # the [n] marker used in the answer
    chunk_id: str
    doc_id: str
    title: str
    section: str
    snippet: str
    score: float


def cited_numbers(answer: str) -> list[int]:
    """Distinct citation numbers in order of first appearance."""
    numbers: list[int] = []
    for group in _MARKER.findall(answer):
        for part in group.split(","):
            n = int(part)
            if n not in numbers:
                numbers.append(n)
    return numbers


def build_citations(
    answer: str, sources: Sequence[SearchResult], snippet_chars: int = 280
) -> list[Citation]:
    """Map the answer's [n] markers to sources. Markers outside 1..len(sources) are ignored."""
    return [
        to_citation(n, sources[n - 1], snippet_chars)
        for n in cited_numbers(answer)
        if 1 <= n <= len(sources)
    ]


def to_citation(number: int, result: SearchResult, snippet_chars: int = 280) -> Citation:
    chunk = result.chunk
    return Citation(
        number=number,
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        title=chunk.title,
        section=chunk.section,
        snippet=_snippet(chunk.text, snippet_chars),
        score=round(result.score, 4),
    )


def _snippet(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rsplit(" ", 1)[0] + "…"
