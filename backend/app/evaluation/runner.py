"""Runs the benchmarks from the admin Tests tab (ideas.md #6) as background jobs.

It reuses the same evaluation code as the CLI and pytest. The web UI never runs pytest or shell
commands. Only one run happens at a time (they compete for the same CPU or API quota). Progress
is kept in memory and every step is saved, so the list survives a restart; a run that was cut
off by a restart is marked "interrupted" when the history opens.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.evaluation.answers import AnswerCheck, summarize
from app.evaluation.dataset import EvalQuestion, load_questions
from app.evaluation.retrieval import QuestionResult, RetrievalReport
from app.rag.pipeline import ChatOptions, ChatResult, RagPipeline
from app.services import Services
from app.stores.events.base import EventStore

logger = logging.getLogger(__name__)

EvalKind = Literal["retrieval", "answers"]


class EvalBusyError(Exception):
    """Another benchmark is still running."""


class _NoEvents(EventStore):
    """Benchmark answers are not chat turns: keep them out of the history, stats and costs."""

    async def record(self, result: ChatResult) -> None:
        return None


@dataclass
class EvalRun:
    id: str
    kind: EvalKind
    provider: str | None
    model: str | None
    status: str  # running | done | failed | cancelled | interrupted
    started_at: str
    total: int
    done: int = 0
    finished_at: str | None = None
    summary: dict[str, Any] | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


SaveRun = Callable[[EvalRun], Awaitable[None]]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class EvalRunner:
    def __init__(self, save: SaveRun, questions: Callable[[], list[EvalQuestion]] = load_questions):
        self._save = save
        self._questions = questions
        self._task: asyncio.Task[None] | None = None
        self.current: EvalRun | None = None

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, kind: EvalKind, services: Services, provider: str | None) -> EvalRun:
        if self.busy:
            raise EvalBusyError("A benchmark is already running. Wait for it or cancel it.")
        questions = self._questions()
        model = None
        if kind == "answers":
            llm = services.llms.get(provider)  # raises for unknown/disabled providers
            provider, model = llm.name, llm.model
        else:
            provider, model = None, services.index.embedding_model
        run = EvalRun(
            id=uuid.uuid4().hex,
            kind=kind,
            provider=provider,
            model=model,
            status="running",
            started_at=_now(),
            total=len(questions),
        )
        await self._save(run)
        self.current = run
        self._task = asyncio.create_task(self._run(run, questions, services))
        return run

    def cancel(self, run_id: str) -> bool:
        if self.busy and self.current and self.current.id == run_id:
            assert self._task is not None
            self._task.cancel()
            return True
        return False

    async def close(self) -> None:
        if self.busy:
            assert self._task is not None
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self, run: EvalRun, questions: list[EvalQuestion], services: Services) -> None:
        try:
            if run.kind == "retrieval":
                await self._retrieval(run, questions, services)
            else:
                await self._answers(run, questions, services)
            run.status = "done"
        except asyncio.CancelledError:
            run.status = "cancelled"
        except Exception as exc:
            logger.exception("Benchmark run %s failed", run.id)
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
        finally:
            run.finished_at = _now()
            await asyncio.shield(self._save(run))

    async def _retrieval(
        self, run: EvalRun, questions: list[EvalQuestion], services: Services
    ) -> None:
        retriever = services.retriever
        k = services.settings.top_k
        rows: list[QuestionResult] = []
        for q in questions:
            started = time.perf_counter()
            result = await retriever.retrieve(q.question, top_k=k)
            retrieved = list(dict.fromkeys(r.chunk.doc_id for r in result.results))
            found = [d for d in q.expected_doc_ids if d in retrieved]
            row = QuestionResult(
                id=q.id,
                answerable=q.answerable,
                expected=q.expected_doc_ids,
                retrieved=retrieved,
                top_score=result.top_score,
                recall=len(found) / len(q.expected_doc_ids) if q.expected_doc_ids else 1.0,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            rows.append(row)
            below = row.top_score < services.settings.min_score
            run.results.append(
                {
                    "id": q.id,
                    "question": q.question,
                    "answerable": q.answerable,
                    # answerable: every expected doc retrieved; unanswerable: refused by MIN_SCORE
                    "passed": row.recall == 1.0 if q.answerable else below,
                    "expected": q.expected_doc_ids,
                    "retrieved": retrieved,
                    "recall": row.recall,
                    "top_score": round(row.top_score, 4),
                    "latency_ms": round(row.latency_ms, 1),
                }
            )
            await self._step(run)
        run.summary = RetrievalReport(k, rows).summary(services.settings.min_score)

    async def _answers(
        self, run: EvalRun, questions: list[EvalQuestion], services: Services
    ) -> None:
        pipeline = RagPipeline(services.retriever, services.llms, _NoEvents())
        checks: list[AnswerCheck] = []
        for q in questions:
            result = await pipeline.answer(q.question, options=ChatOptions(provider=run.provider))
            check = AnswerCheck(q, result)
            checks.append(check)
            run.results.append(
                {
                    "id": q.id,
                    "question": q.question,
                    "answerable": q.answerable,
                    "passed": check.passed,
                    "refused": result.refused,
                    "expected": q.expected_doc_ids,
                    "cited": check.cited_docs,
                    "key_facts": q.key_facts,
                    "facts_found": check.facts_found,
                    "answer": result.answer,
                    "total_ms": round(result.timings.total_ms, 1),
                }
            )
            await self._step(run)
        run.summary = summarize(checks)

    async def _step(self, run: EvalRun) -> None:
        run.done += 1
        await self._save(run)
