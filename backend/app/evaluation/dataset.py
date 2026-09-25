from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_QUESTIONS = Path("tests/eval/questions.yaml")


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    answerable: bool
    expected_doc_ids: list[str] = field(default_factory=list)
    lang: str = "en"
    key_facts: list[str] = field(default_factory=list)


def load_questions(path: Path = DEFAULT_QUESTIONS) -> list[EvalQuestion]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        EvalQuestion(
            id=q["id"],
            question=q["question"],
            answerable=q["answerable"],
            expected_doc_ids=list(q.get("expected_doc_ids") or []),
            lang=q.get("lang", "en"),
            key_facts=list(q.get("key_facts") or []),
        )
        for q in data["questions"]
    ]
