from itertools import pairwise

import pytest

from app.rag.chunking import SECTION_SEPARATOR as SEP
from app.rag.chunking import ChunkingConfig, chunk_document, parse_document

ARTICLE = """---
id: kb-900
title: Test Guide
lang: de
---

# Test Guide

Intro paragraph.

## Setup

Setup text.

### Step one

Step text.

## Empty parent

### Child

Child text.

## Limits

| Plan | Limit |
|---|---|
| A | 1 |
"""


def test_parse_front_matter() -> None:
    doc = parse_document(ARTICLE, source="x.md")
    assert (doc.doc_id, doc.title, doc.lang) == ("kb-900", "Test Guide", "de")
    assert doc.body.lstrip().startswith("# Test Guide")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# No front matter", "missing YAML front matter"),
        ("---\ntitle: T\n---\nbody", "missing 'id'"),
        ("---\nid: kb-1\n---\nbody", "missing 'title'"),
    ],
)
def test_parse_rejects_invalid_documents(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_document(text)


def test_chunks_follow_heading_structure() -> None:
    chunks = chunk_document(parse_document(ARTICLE))
    assert [(c.chunk_id, c.section, c.text) for c in chunks] == [
        ("kb-900#000", "", "Intro paragraph."),
        ("kb-900#001", "Setup", "Setup text."),
        ("kb-900#002", f"Setup{SEP}Step one", "Step text."),
        ("kb-900#003", f"Empty parent{SEP}Child", "Child text."),
        ("kb-900#004", "Limits", "| Plan | Limit |\n|---|---|\n| A | 1 |"),
    ]
    assert all(c.doc_id == "kb-900" and c.title == "Test Guide" and c.lang == "de" for c in chunks)


def test_embedding_text_includes_section() -> None:
    chunk = chunk_document(parse_document(ARTICLE))[2]
    assert chunk.embedding_text() == f"Setup{SEP}Step one\n\nStep text."


def _section(paragraphs: list[str]) -> str:
    return "---\nid: d\ntitle: T\n---\n## Long\n\n" + "\n\n".join(paragraphs)


def test_long_section_is_packed_with_block_overlap() -> None:
    paragraphs = [" ".join([f"p{i}w{j}" for j in range(10)]) for i in range(6)]  # 6 x 10 words
    chunks = chunk_document(
        parse_document(_section(paragraphs)), ChunkingConfig(max_words=25, overlap_words=10)
    )
    texts = [c.text.split("\n\n") for c in chunks]
    assert all(len(c.text.split()) <= 25 for c in chunks)
    # Each window starts with the last paragraph of the previous one (10-word overlap).
    for previous, current in pairwise(texts):
        assert current[0] == previous[-1]
    covered = {p for window in texts for p in window}
    assert covered == set(paragraphs)


def test_oversized_block_is_split_by_words() -> None:
    words = [f"w{i}" for i in range(50)]
    chunks = chunk_document(
        parse_document(_section([" ".join(words)])), ChunkingConfig(max_words=20, overlap_words=5)
    )
    pieces = [c.text.split() for c in chunks]
    assert all(len(p) <= 20 for p in pieces)
    assert pieces[0][-5:] == pieces[1][:5]  # word overlap between pieces
    assert pieces[-1][-1] == "w49"  # nothing lost at the end


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        ChunkingConfig(max_words=10, overlap_words=10)
