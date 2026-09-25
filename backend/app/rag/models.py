from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Document:
    """A KB article: front-matter metadata plus the Markdown body."""

    doc_id: str
    title: str
    body: str
    lang: str = "en"
    source: str = ""  # file name, for diagnostics
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Chunk:
    """A retrievable passage. `section` is the heading path shown in citations."""

    chunk_id: str
    doc_id: str
    title: str
    section: str
    text: str
    lang: str = "en"

    def embedding_text(self) -> str:
        # Headings carry much of the meaning of short sections ("Certificate rotation").
        return f"{self.section}\n\n{self.text}" if self.section else self.text
