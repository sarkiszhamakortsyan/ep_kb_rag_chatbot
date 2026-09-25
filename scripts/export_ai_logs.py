#!/usr/bin/env python3
"""Export Claude Code session transcripts (JSONL) to readable Markdown in documentation/ai-logs/.

The assignment requires the AI-assistant conversation logs to be committed. A Claude Code
Stop/SessionEnd hook (.claude/settings.json) runs this after every assistant turn, so the
Markdown log is always current.

Usage:
  scripts/export_ai_logs.py --hook            # read the hook JSON (transcript_path) from stdin
  scripts/export_ai_logs.py --all             # export every session of this project
  scripts/export_ai_logs.py path/to/session.jsonl ...

Standard library only. Known secret formats are redacted before anything is written.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "documentation" / "ai-logs"
# Claude Code stores transcripts under ~/.claude/projects/<cwd, non-alphanumerics -> "-">/.
PROJECT_TRANSCRIPTS = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(REPO_ROOT))

MAX_TOOL_INPUT = 1500  # characters of a tool call's input shown in the log
MAX_TOOL_RESULT = 1500  # characters of a tool result shown in the log
MAX_INJECTED_TEXT = 600  # skill instructions and other injected text are long; keep a preview

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),  # Anthropic keys
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key ids
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),  # Groq keys
    # KEY=value / "token": "value" with a long, secret-looking value
    re.compile(
        r"(?i)((?:api[_-]?key|secret|token|password|passwd)[\"']?\s*[:=]\s*[\"']?)"
        r"((?=[A-Za-z0-9_\-./+]*\d)[A-Za-z0-9_\-./+]{16,})"  # must contain a digit
    ),
]
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n… [{len(text) - limit} more characters omitted]"


def fence(text: str) -> str:
    """A code fence longer than any backtick run inside the text."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}\n{text}\n{ticks}"


def details(summary: str, body: str) -> str:
    return f"<details>\n<summary>{summary}</summary>\n\n{fence(body)}\n\n</details>\n"


def result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif item.get("type") == "image":
                    parts.append("[image]")
        return "\n".join(parts)
    return ""


def tool_input_summary(name: str, tool_input: dict[str, object]) -> str:
    """The most informative field of a tool call, shown in the <summary> line."""
    for key in ("description", "file_path", "command", "query", "url", "skill", "pattern"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            value = value.splitlines()[0]
            return f"{name}: {value[:120]}"
    return name


def format_time(timestamp: str | None) -> str:
    if not timestamp:
        return ""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return timestamp


def convert(transcript: Path) -> tuple[str, str, str] | None:
    """Return (session_id, first timestamp, markdown) or None for an empty session."""
    records = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue

    session_id = transcript.stem
    title = next((r.get("aiTitle") or r.get("title") for r in records if r.get("type") == "ai-title"), None)
    first_ts = next((r["timestamp"] for r in records if r.get("timestamp")), "")
    out: list[str] = []
    prompts = 0

    for record in records:
        if record.get("isSidechain") or record.get("type") not in ("user", "assistant"):
            continue
        message = record.get("message") or {}
        content = message.get("content")

        if record["type"] == "user":
            if isinstance(content, str):
                text = SYSTEM_REMINDER.sub("", content).strip()
                if not text or record.get("isMeta"):
                    continue
                prompts += 1
                out.append(f"\n---\n\n## 🧑 User — {format_time(record.get('timestamp'))}\n\n{text}\n")
                continue
            for block in content or []:
                if block.get("type") == "tool_result":
                    body = clip(result_text(block.get("content")), MAX_TOOL_RESULT)
                    label = "Tool error" if block.get("is_error") else "Tool result"
                    if body:
                        out.append(details(label, body))
                elif block.get("type") == "text":
                    text = SYSTEM_REMINDER.sub("", str(block.get("text", ""))).strip()
                    if text:
                        # Skill instructions and other text injected into the conversation.
                        out.append(details("Injected context (skill instructions etc.)", clip(text, MAX_INJECTED_TEXT)))
        else:
            for block in content or []:
                if block.get("type") == "text" and str(block.get("text", "")).strip():
                    out.append(f"\n### 🤖 Claude\n\n{block['text'].strip()}\n")
                elif block.get("type") == "tool_use":
                    tool_input = block.get("input") or {}
                    summary = tool_input_summary(str(block.get("name")), tool_input)
                    body = clip(json.dumps(tool_input, indent=2, ensure_ascii=False), MAX_TOOL_INPUT)
                    out.append(details(f"🔧 {summary.replace('<', '&lt;')}", body))
                # "thinking" blocks are internal reasoning and are not exported.

    if not prompts:
        return None
    header = [
        f"# AI assistant session: {title or session_id}",
        "",
        "- **Tool:** Claude Code (CLI)",
        f"- **Session id:** `{session_id}`",
        f"- **Started:** {format_time(first_ts)}",
        f"- **User prompts:** {prompts}",
        "",
        "Exported automatically from the Claude Code transcript by `scripts/export_ai_logs.py`. "
        "Tool calls and results are collapsed and truncated; internal reasoning is omitted; "
        "secrets are redacted.",
    ]
    return session_id, first_ts, redact("\n".join(header) + "\n" + "".join(out))


def export(transcript: Path) -> Path | None:
    converted = convert(transcript)
    if converted is None:
        return None
    session_id, first_ts, markdown = converted
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / f"{first_ts[:10] or 'session'}_{session_id[:8]}.md"
    if not target.exists() or target.read_text(encoding="utf-8") != markdown:
        target.write_text(markdown, encoding="utf-8")
    return target


def write_index() -> None:
    rows = []
    for log in sorted(OUT_DIR.glob("*_*.md")):
        first = log.read_text(encoding="utf-8").splitlines()[0]
        rows.append(f"- [{first.removeprefix('# AI assistant session: ')}]({log.name})")
    index = (
        "# AI assistant conversation logs\n\n"
        "Complete Claude Code sessions used to build this project, exported to Markdown "
        "after every assistant turn by a Claude Code hook (`.claude/settings.json` -> "
        "`scripts/export_ai_logs.py`).\n\n" + "\n".join(rows) + "\n"
    )
    (OUT_DIR / "README.md").write_text(index, encoding="utf-8")


def main(argv: list[str]) -> int:
    if "--hook" in argv:
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            return 0
        path = payload.get("transcript_path")
        transcripts = [Path(path)] if path else []
    elif "--all" in argv:
        transcripts = sorted(PROJECT_TRANSCRIPTS.glob("*.jsonl"))
    else:
        transcripts = [Path(a) for a in argv if not a.startswith("--")]

    for transcript in transcripts:
        if transcript.exists():
            target = export(transcript)
            if target and "--hook" not in argv:
                print(f"exported {transcript.name} -> {target.relative_to(REPO_ROOT)}")
    if OUT_DIR.exists():
        write_index()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
