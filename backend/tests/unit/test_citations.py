from app.rag.citations import build_citations, cited_numbers
from app.rag.models import Chunk
from app.rag.prompts import build_user_message, load_prompt
from app.stores.vector.base import SearchResult


def result(n: int, text: str = "Some text.", section: str = "Sec") -> SearchResult:
    return SearchResult(Chunk(f"kb-{n}#000", f"kb-{n}", f"Doc {n}", section, text), 0.5 + n / 100)


def test_cited_numbers_handles_all_marker_styles() -> None:
    answer = "A [2]. B [1][3]. C [2, 4]. D [1,2]. Not a marker: [x], [ 5 ]"
    assert cited_numbers(answer) == [2, 1, 3, 4]


def test_build_citations_maps_markers_to_sources_in_order() -> None:
    sources = [result(1), result(2), result(3)]
    citations = build_citations("First [3]. Then [1]. Again [3].", sources)
    assert [(c.number, c.doc_id) for c in citations] == [(3, "kb-3"), (1, "kb-1")]
    assert citations[0].score == 0.53
    assert citations[0].section == "Sec"


def test_out_of_range_markers_are_ignored() -> None:
    assert build_citations("Made up [7] and [0].", [result(1)]) == []


def test_snippet_is_flattened_and_truncated_at_a_word() -> None:
    text = "word " * 100
    citation = build_citations("[1]", [result(1, text=text)], snippet_chars=23)[0]
    assert citation.snippet == "word word word word…"


def test_user_message_numbers_sources_and_ends_with_question() -> None:
    message = build_user_message("  How long?  ", [result(1, "Alpha."), result(2, section="")])
    assert '<source id="1">\nDocument: Doc 1\nSection: Sec\n\nAlpha.\n</source>' in message
    assert '<source id="2">\nDocument: Doc 2\n\nSome text.' in message  # no empty section line
    assert message.endswith("</sources>\n\nQuestion: How long?")


def test_prompt_templates_are_loaded_from_files() -> None:
    system = load_prompt("system")
    assert "Answer only from the sources" in system
    assert "do not include any citation" in system
    assert "Internal SME Request" in load_prompt("no_answer")


def test_snippet_strips_markdown() -> None:
    text = "- **HTTP 429 `RATE_LIMITED`**: retry later.\n\n| Plan | Limit |\n|---|---|\n| A | 60 |"
    citation = build_citations("[1]", [result(1, text=text)])[0]
    assert citation.snippet == "HTTP 429 RATE_LIMITED: retry later. Plan · Limit; A · 60"
