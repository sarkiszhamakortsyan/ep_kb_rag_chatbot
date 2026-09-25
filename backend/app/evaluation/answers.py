"""End-to-end answer benchmark: runs the full pipeline over the eval set.

Checks per question: answerable ones are answered and cite an expected document, and their
key facts appear in the answer; unanswerable ones are refused. Calls the real LLM, so it
costs tokens with Claude.

CLI: `uv run python -m app.evaluation.answers [--provider anthropic] [--ids q01,q16] [--show]`
"""

import argparse
import asyncio
import statistics
from dataclasses import dataclass

from app.evaluation.dataset import EvalQuestion, load_questions
from app.rag.pipeline import ChatOptions, ChatResult, RagPipeline


@dataclass(frozen=True)
class AnswerCheck:
    question: EvalQuestion
    result: ChatResult

    @property
    def cited_docs(self) -> list[str]:
        return list(dict.fromkeys(c.doc_id for c in self.result.citations))

    @property
    def facts_found(self) -> list[str]:
        answer = self.result.answer.lower()
        return [f for f in self.question.key_facts if f.lower() in answer]

    @property
    def passed(self) -> bool:
        if not self.question.answerable:
            return self.result.refused
        return (
            not self.result.refused
            and bool(set(self.cited_docs) & set(self.question.expected_doc_ids))
            and len(self.facts_found) == len(self.question.key_facts)
        )


async def evaluate_answers(
    pipeline: RagPipeline, questions: list[EvalQuestion], options: ChatOptions | None = None
) -> list[AnswerCheck]:
    return [AnswerCheck(q, await pipeline.answer(q.question, options=options)) for q in questions]


def format_checks(checks: list[AnswerCheck], show_answers: bool = False) -> str:
    lines = [
        f"{'id':<5} {'ok':<4} {'refused':<14} {'cited':<16} {'facts':<6}"
        f" {'ttft s':>7} {'total s':>8} {'in/out tok':>11}"
    ]
    for c in checks:
        r = c.result
        facts = (
            f"{len(c.facts_found)}/{len(c.question.key_facts)}" if c.question.answerable else "-"
        )
        ttft = (
            f"{r.timings.time_to_first_token_ms / 1000:.1f}"
            if r.timings.time_to_first_token_ms
            else "-"
        )
        lines.append(
            f"{c.question.id:<5} {'PASS' if c.passed else 'FAIL':<4} {r.refusal_reason or '-':<14}"
            f" {','.join(c.cited_docs) or '-':<16} {facts:<6} {ttft:>7}"
            f" {r.timings.total_ms / 1000:>8.1f}"
            f" {r.usage.input_tokens:>5}/{r.usage.output_tokens:<5}"
        )
        if show_answers:
            lines.append("      " + r.answer.replace("\n", "\n      ") + "\n")
    answerable = [c for c in checks if c.question.answerable]
    unanswerable = [c for c in checks if not c.question.answerable]
    llm_turns = [c.result for c in checks if c.result.provider]
    lines.append("")
    lines.append(
        f"passed {sum(c.passed for c in checks)}/{len(checks)}"
        f" | answerable {sum(c.passed for c in answerable)}/{len(answerable)}"
        f" | refused correctly {sum(c.passed for c in unanswerable)}/{len(unanswerable)}"
    )
    if llm_turns:
        lines.append(
            f"median total {statistics.median(r.timings.total_ms for r in llm_turns) / 1000:.1f} s"
            f" | tokens in {sum(r.usage.input_tokens for r in llm_turns)}"
            f" (cache read {sum(r.usage.cache_read_input_tokens for r in llm_turns)})"
            f" out {sum(r.usage.output_tokens for r in llm_turns)}"
            f" | model {llm_turns[0].model}"
        )
    return "\n".join(lines)


async def _main(provider: str | None, ids: set[str] | None, show: bool) -> None:
    from app.core.config import get_settings
    from app.services import create_services

    services = await create_services(get_settings())
    try:
        questions = [q for q in load_questions() if not ids or q.id in ids]
        checks = await evaluate_answers(
            services.pipeline, questions, ChatOptions(provider=provider)
        )
    finally:
        await services.aclose()
    print(format_checks(checks, show))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", help="LLM provider (default: LLM_PROVIDER)")
    parser.add_argument("--ids", help="comma-separated question ids, e.g. q01,q16")
    parser.add_argument("--show", action="store_true", help="print the answers")
    args = parser.parse_args()
    asyncio.run(_main(args.provider, set(args.ids.split(",")) if args.ids else None, args.show))
