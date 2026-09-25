"""Retrieval-quality benchmark: does the right document come back, and how confidently?

Used by `pytest -m eval` and (later) the hidden Tests admin tab (ideas.md #6).
CLI: `uv run python -m app.evaluation.retrieval [--k 5]`
"""

import asyncio
import statistics
import sys
from dataclasses import dataclass

from app.evaluation.dataset import EvalQuestion, load_questions
from app.rag.retrieval import Retriever


@dataclass(frozen=True)
class QuestionResult:
    id: str
    answerable: bool
    expected: list[str]
    retrieved: list[str]  # distinct doc ids in rank order
    top_score: float
    recall: float  # share of expected docs found in the top k (1.0 for unanswerable)
    latency_ms: float


@dataclass(frozen=True)
class RetrievalReport:
    k: int
    results: list[QuestionResult]

    @property
    def answerable(self) -> list[QuestionResult]:
        return [r for r in self.results if r.answerable]

    @property
    def unanswerable(self) -> list[QuestionResult]:
        return [r for r in self.results if not r.answerable]

    @property
    def mean_recall(self) -> float:
        return statistics.fmean(r.recall for r in self.answerable)

    @property
    def hit_rate(self) -> float:
        """Share of answerable questions with at least one expected doc in the top k."""
        return statistics.fmean(1.0 if r.recall > 0 else 0.0 for r in self.answerable)

    def refusal_accuracy(self, min_score: float) -> float:
        """With this threshold: answerable kept + unanswerable refused, over all questions."""
        correct = sum(r.top_score >= min_score for r in self.answerable) + sum(
            r.top_score < min_score for r in self.unanswerable
        )
        return correct / len(self.results)


async def evaluate_retrieval(
    retriever: Retriever, questions: list[EvalQuestion], k: int
) -> RetrievalReport:
    results = []
    for q in questions:
        retrieval = await retriever.retrieve(q.question, top_k=k)
        retrieved = list(dict.fromkeys(r.chunk.doc_id for r in retrieval.results))
        found = [d for d in q.expected_doc_ids if d in retrieved]
        results.append(
            QuestionResult(
                id=q.id,
                answerable=q.answerable,
                expected=q.expected_doc_ids,
                retrieved=retrieved,
                top_score=retrieval.top_score,
                recall=len(found) / len(q.expected_doc_ids) if q.expected_doc_ids else 1.0,
                latency_ms=retrieval.embed_ms + retrieval.search_ms,
            )
        )
    return RetrievalReport(k=k, results=results)


def format_report(report: RetrievalReport, min_score: float) -> str:
    lines = [f"{'id':<5} {'ans':<4} {'recall':>6} {'top':>6} {'ms':>6}  expected -> retrieved"]
    for r in report.results:
        lines.append(
            f"{r.id:<5} {'yes' if r.answerable else 'no':<4} {r.recall:>6.2f} {r.top_score:>6.3f}"
            f" {r.latency_ms:>6.0f}  {','.join(r.expected) or '-'} -> {','.join(r.retrieved)}"
        )
    answerable = sorted(r.top_score for r in report.answerable)
    unanswerable = sorted(r.top_score for r in report.unanswerable)
    lines += [
        "",
        f"k={report.k}  mean recall={report.mean_recall:.2f}  hit rate={report.hit_rate:.2f}",
        f"top score, answerable:   min={answerable[0]:.3f}"
        f" median={statistics.median(answerable):.3f}",
        f"top score, unanswerable: max={unanswerable[-1]:.3f}" if unanswerable else "",
        f"MIN_SCORE={min_score}: refusal accuracy={report.refusal_accuracy(min_score):.2f}",
    ]
    return "\n".join(lines)


async def _main(k: int | None) -> None:
    from app.core.config import get_settings
    from app.providers.embeddings.registry import build_embedding_registry
    from app.rag.ingest import build_or_load_index

    settings = get_settings()
    registry = build_embedding_registry(settings)
    try:
        embedder = registry.get()
        store, _ = await build_or_load_index(
            settings.kb_dir, settings.index_dir, embedder, settings.chunking()
        )
        retriever = Retriever(embedder, store, top_k=settings.top_k, min_score=settings.min_score)
        report = await evaluate_retrieval(retriever, load_questions(), k or settings.top_k)
    finally:
        await registry.aclose()
    print(format_report(report, settings.min_score))


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(_main(int(args[args.index("--k") + 1]) if "--k" in args else None))
