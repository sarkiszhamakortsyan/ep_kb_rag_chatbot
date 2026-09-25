import pytest

from app.evaluation.answers import AnswerCheck, evaluate_answers, summarize
from app.evaluation.dataset import EvalQuestion, load_questions
from app.evaluation.retrieval import evaluate_retrieval
from app.evaluation.stats import latency_summary, percentile
from tests.fakes import FakeLLM
from tests.unit.test_pipeline import make_pipeline

pytestmark = pytest.mark.anyio


def test_percentile_nearest_rank() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 100.0
    assert percentile([], 50) is None
    assert latency_summary([3.0, 1.0, 2.0]) == {"p50_ms": 2.0, "p95_ms": 3.0, "max_ms": 3.0}


def test_eval_set_is_well_formed() -> None:
    questions = load_questions()
    assert len({q.id for q in questions}) == len(questions)
    assert all(q.expected_doc_ids for q in questions if q.answerable)
    assert all(not q.expected_doc_ids for q in questions if not q.answerable)
    assert sum(not q.answerable for q in questions) >= 3


QUESTIONS = [
    EvalQuestion("a1", "How long are backups retained?", True, ["kb-3"], key_facts=["35 days"]),
    EvalQuestion("a2", "How are webhooks signed?", True, ["kb-4"], key_facts=["HMAC"]),
    EvalQuestion("u1", "zebra quantum football", False),
]


async def test_answer_benchmark_scores_pass_and_fail() -> None:
    # The fake LLM always answers about backups, so the webhook question fails its checks.
    pipeline, _ = await make_pipeline({"fake": FakeLLM("Backups are retained for 35 days [1].")})
    checks = await evaluate_answers(pipeline, QUESTIONS)
    assert [c.passed for c in checks] == [True, False, True]

    summary = summarize(checks)
    assert summary["passed"] == 2
    assert summary["answer_accuracy"] == 0.5
    assert summary["refusal_accuracy"] == 1.0
    assert summary["key_fact_coverage"] == 0.5
    assert summary["failed_ids"] == ["a2"]
    assert summary["total_latency"]["p50_ms"] is not None  # type: ignore[index]


async def test_answer_check_requires_expected_citation() -> None:
    pipeline, _ = await make_pipeline({"fake": FakeLLM("Retained 35 days [1].")})
    result = await pipeline.answer("How long are backups retained?")
    wrong_doc = EvalQuestion("x", "q", True, ["kb-9"], key_facts=["35 days"])
    assert not AnswerCheck(wrong_doc, result).passed


async def test_retrieval_summary() -> None:
    pipeline, _ = await make_pipeline({"fake": FakeLLM()})
    report = await evaluate_retrieval(pipeline._retriever, QUESTIONS, k=2)
    summary = report.summary(min_score=0.4)
    assert summary["hit_rate"] == 1.0
    assert summary["refusal_accuracy_at_min_score"] == 1.0
    assert summary["retrieval_latency"]["p95_ms"] is not None  # type: ignore[index]
