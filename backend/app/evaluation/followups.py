"""Follow-up benchmark (ideas.md #5): two-turn conversations through the full pipeline.

Each follow-up is asked twice: in its conversation (rewritten with the earlier turn) and on its
own (no context), to show what the rewriting adds. Calls the real LLM.

CLI: `uv run python -m app.evaluation.followups [--provider anthropic] [--show] [--json out.json]`
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.rag.pipeline import ChatOptions, ChatResult, RagPipeline
from app.stores.events.memory import InMemoryConversations

DEFAULT_FOLLOWUPS = Path("tests/eval/followups.yaml")


@dataclass(frozen=True)
class Conversation:
    id: str
    first: str
    follow_up: str
    expected_doc_ids: list[str]
    key_facts: list[str]  # "a|b" = either
    lang: str = "en"


def load_conversations(path: Path = DEFAULT_FOLLOWUPS) -> list[Conversation]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Conversation(
            id=c["id"],
            first=c["first"],
            follow_up=c["follow_up"],
            expected_doc_ids=list(c["expected_doc_ids"]),
            key_facts=list(c["key_facts"]),
            lang=c.get("lang", "en"),
        )
        for c in data["conversations"]
    ]


def passed(conversation: Conversation, result: ChatResult) -> bool:
    answer = result.answer.lower()
    cited = {c.doc_id for c in result.citations}
    facts = all(
        any(alt.lower() in answer for alt in fact.split("|")) for fact in conversation.key_facts
    )
    return not result.refused and bool(cited & set(conversation.expected_doc_ids)) and facts


async def evaluate_followups(
    pipeline: RagPipeline, conversations: list[Conversation], provider: str | None = None
) -> list[dict[str, Any]]:
    options = ChatOptions(provider=provider)
    rows = []
    for c in conversations:
        first = await pipeline.answer(c.first, options=options)
        with_context = await pipeline.answer(
            c.follow_up, conversation_id=first.conversation_id, options=options
        )
        alone = await pipeline.answer(c.follow_up, options=options)
        rows.append(
            {
                "id": c.id,
                "follow_up": c.follow_up,
                "standalone_question": with_context.standalone_question,
                "passed_with_context": passed(c, with_context),
                "passed_alone": passed(c, alone),
                "answer": with_context.answer,
                "rewrite_ms": with_context.timings.rewrite_ms,
                "total_ms": with_context.timings.total_ms,
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "conversations": len(rows),
        "passed_with_context": sum(r["passed_with_context"] for r in rows),
        "passed_alone": sum(r["passed_alone"] for r in rows),
        "rewrite_ms_median": sorted(r["rewrite_ms"] for r in rows)[len(rows) // 2]
        if rows
        else None,
    }


async def _main(provider: str | None, show: bool, json_path: str | None) -> None:
    from app.core.config import get_settings
    from app.services import create_services

    services = await create_services(get_settings(), InMemoryConversations())
    try:
        rows = await evaluate_followups(services.pipeline, load_conversations(), provider)
    finally:
        await services.aclose()
    for r in rows:
        mark = "PASS" if r["passed_with_context"] else "FAIL"
        print(
            f"{r['id']}  {mark}  (alone: {'pass' if r['passed_alone'] else 'fail'})  "
            f"{r['follow_up']!r} -> {r['standalone_question']!r}  "
            f"rewrite {r['rewrite_ms'] / 1000:.1f} s"
        )
        if show:
            print("      " + r["answer"].replace("\n", "\n      ") + "\n")
    summary = summarize(rows)
    print(
        f"\nfollow-ups passed with context {summary['passed_with_context']}/{len(rows)}, "
        f"alone {summary['passed_alone']}/{len(rows)}"
    )
    if json_path:
        Path(json_path).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--json")
    args = parser.parse_args()
    asyncio.run(_main(args.provider, args.show, args.json))
