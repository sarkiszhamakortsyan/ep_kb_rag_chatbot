"""Command-line client for the knowledge-base API (ideas.md: use it over a CLI).

It calls the HTTP API, so it works against the Docker stack (default http://localhost:8080) or a
local backend (--url http://localhost:8000).

  uv run python -m app.cli ask "How long are backups kept?" [--model anthropic]
                               [--language de] [--detailed] [--json]
  uv run python -m app.cli ask "/claude How long are backups kept?"   model chosen by command
  uv run python -m app.cli                 interactive session (/help, /claude, /local, /models)
  uv run python -m app.cli health
  uv run python -m app.cli providers

Exit codes: 0 answered, 2 not covered by the knowledge base, 1 error.
Colours only on a terminal, and never when NO_COLOR is set.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, replace
from typing import Any, TextIO

from app.cli.api import ApiError, KbClient
from app.cli.models import ModelCommand, label, model_commands, model_list, split_command
from app.rag.chunking import SECTION_SEPARATOR

DEFAULT_URL = os.environ.get("OMNICORP_KB_URL", "http://localhost:8080")
EXIT_OK, EXIT_ERROR, EXIT_NOT_COVERED = 0, 1, 2
LANGUAGES = ("en", "de", "fr", "es", "it", "pt", "nl", "pl")

HELP = """Commands:
  /new              start a new conversation
  /claude, /local   switch the model (also /anthropic, /ollama, /ministral; see /models)
  /claude QUESTION  ask one question with that model; the selection stays
  /models           list the models and their commands
  /model NAME       use a model provider (e.g. anthropic, ollama); /model alone = default
  /lang CODE        answer language (en, de, fr, ...); /lang auto = the question's language
  /detail on|off    detailed answers
  /help             this help
  /quit             leave (or Ctrl+D)"""


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def warn(self, text: str) -> str:
        return self._wrap("33", text)

    def error(self, text: str) -> str:
        return self._wrap("31", text)


@dataclass
class Session:
    provider: str | None = None
    language: str | None = None
    detailed: bool = False
    conversation_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def body(self, question: str) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self.provider:
            options["provider"] = self.provider
        if self.language:
            options["language"] = self.language
        if self.detailed:
            options["detail"] = "detailed"
        body: dict[str, Any] = {"message": question, "options": options}
        if self.conversation_id:
            body["conversation_id"] = self.conversation_id
        return body


def ask(client: KbClient, session: Session, question: str, out: TextIO, style: Style) -> int:
    """Streams one answer, then prints its sources. Returns an exit code."""
    result: dict[str, Any] | None = None
    for event, data in client.stream(session.body(question)):
        if event == "meta":
            session.conversation_id = data["conversation_id"]
        elif event == "token":
            out.write(data["text"])
            out.flush()
        elif event == "done":
            result = data
        elif event == "error":
            out.write("\n")
            raise ApiError(data["code"], data["message"])
    if result is None:
        raise ApiError("stream_interrupted", "The answer was interrupted.")
    out.write("\n")
    print_sources(result, out, style)
    if result["refused"]:
        out.write(style.warn("Not covered by the knowledge base.") + "\n")
        return EXIT_NOT_COVERED
    return EXIT_OK


def print_sources(result: dict[str, Any], out: TextIO, style: Style) -> None:
    if result["citations"]:
        out.write("\n" + style.bold("Sources") + "\n")
        for c in result["citations"]:
            section = f"{SECTION_SEPARATOR}{c['section']}" if c["section"] else ""
            out.write(
                f"  [{c['number']}] {c['title']}{section} {style.dim('(' + c['doc_id'] + ')')}\n"
            )
    seconds = result["timings"]["total_ms"] / 1000
    model = result["model"] or "no model"
    out.write(style.dim(f"{model} · {seconds:.1f} s") + "\n")


def repl(client: KbClient, session: Session, inp: TextIO, out: TextIO, style: Style) -> int:
    out.write(
        style.bold("OmniCorp knowledge base") + style.dim("  (type /help, /quit to leave)") + "\n"
    )
    commands = load_commands(client)
    while True:
        out.write("\n> ")
        out.flush()
        line = inp.readline()
        if not line:  # Ctrl+D
            out.write("\n")
            return EXIT_OK
        text = line.strip()
        if not text:
            continue
        # "/word ..." is a command; "/v3/records:batch ..." and other paths are questions.
        if text.startswith("/") and split_command(text) is not None:
            if model_command(client, session, commands, text, out, style):
                continue
            if command(text, session, out, style) == "quit":
                return EXIT_OK
            continue
        try:
            ask(client, session, text, out, style)
        except ApiError as exc:
            out.write(style.error(f"Error: {exc}") + "\n")


def load_commands(client: KbClient) -> dict[str, ModelCommand]:
    """Model commands for the enabled providers; none if the API cannot be reached yet."""
    try:
        return model_commands(client.get("/providers")["providers"])
    except (ApiError, ValueError, KeyError, TypeError):
        return {}


def model_command(
    client: KbClient,
    session: Session,
    commands: dict[str, ModelCommand],
    text: str,
    out: TextIO,
    style: Style,
) -> bool:
    """Handles /models, /<model> and /<model> <question>; False if `text` is another command."""
    parsed = split_command(text)
    if parsed is None:
        return False
    name, question = parsed
    if name == "models":
        out.write(model_list(commands, session.provider) + "\n")
        return True
    found = commands.get(name)
    if found is None:
        return False
    provider = found.provider
    if not provider.get("available", True):
        detail = f": {provider['detail']}" if provider.get("detail") else ""
        out.write(style.warn(f"{label(provider)} is not available right now{detail}.") + "\n")
    elif question:
        # This question only: the selection stays, the conversation continues.
        one_off = replace(session, provider=provider["name"])
        try:
            ask(client, one_off, question, out, style)
        except ApiError as exc:
            out.write(style.error(f"Error: {exc}") + "\n")
        session.conversation_id = one_off.conversation_id
    else:
        session.provider = provider["name"]
        out.write(style.dim(f"Model switched to {label(provider)}.") + "\n")
    return True


def command(text: str, session: Session, out: TextIO, style: Style) -> str | None:
    name, _, arg = text.partition(" ")
    arg = arg.strip()
    if name in ("/quit", "/exit"):
        return "quit"
    if name == "/new":
        session.conversation_id = None
        out.write(style.dim("New conversation.") + "\n")
    elif name == "/model":
        session.provider = arg or None
        out.write(style.dim(f"Model provider: {session.provider or 'default'}") + "\n")
    elif name == "/lang":
        if arg in ("", "auto"):
            session.language = None
        elif arg in LANGUAGES:
            session.language = arg
        else:
            out.write(
                style.error(f"Unknown language; use auto or one of {', '.join(LANGUAGES)}") + "\n"
            )
            return None
        out.write(style.dim(f"Answer language: {session.language or 'auto'}") + "\n")
    elif name == "/detail":
        session.detailed = arg == "on"
        out.write(style.dim(f"Detailed answers: {'on' if session.detailed else 'off'}") + "\n")
    elif name == "/help":
        out.write(HELP + "\n")
    else:
        out.write(style.error(f"Unknown command {name}. Type /help.") + "\n")
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Ask the OmniCorp knowledge base from a terminal."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help=f"API address (default {DEFAULT_URL})")
    sub = parser.add_subparsers(dest="cmd")
    ask_cmd = sub.add_parser("ask", help="ask one question")
    ask_cmd.add_argument("question")
    ask_cmd.add_argument("--model", help="model provider, e.g. anthropic or ollama")
    ask_cmd.add_argument("--language", choices=LANGUAGES, help="answer language")
    ask_cmd.add_argument("--detailed", action="store_true", help="ask for a detailed answer")
    ask_cmd.add_argument("--json", action="store_true", help="print the full JSON result")
    sub.add_parser("health", help="show whether the service is ready")
    sub.add_parser("providers", help="list the model providers")
    return parser


def main(
    argv: list[str],
    *,
    client: KbClient | None = None,
    inp: TextIO | None = None,
    out: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    out = out or sys.stdout
    inp = inp or sys.stdin
    style = Style(out.isatty() and "NO_COLOR" not in os.environ)
    kb = client or KbClient(args.url)
    try:
        if args.cmd == "ask":
            session = Session(provider=args.model, language=args.language, detailed=args.detailed)
            question = args.question
            # `ask "/claude How long ...?"` picks the model like the interactive session does.
            parsed = split_command(question)
            if parsed is not None and parsed[0] != "models":
                found = load_commands(kb).get(parsed[0])
                if found is None:
                    raise ApiError("unknown_model", f"Unknown model command /{parsed[0]}.")
                if not parsed[1]:
                    raise ApiError("no_question", f"Add a question after /{parsed[0]}.")
                session.provider, question = found.provider["name"], parsed[1]
            if args.json:
                result = kb.chat(session.body(question))
                out.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
                return EXIT_NOT_COVERED if result["refused"] else EXIT_OK
            return ask(kb, session, question, out, style)
        if args.cmd == "health":
            health = kb.get("/health")
            index = health["index"]
            state = "ready" if health["ready"] else "not ready"
            out.write(
                f"{health['status']} ({state}) · {index['documents']} documents, "
                f"{index['chunks']} chunks · default model {health['llm_provider']}\n"
            )
            return EXIT_OK if health["ready"] else EXIT_ERROR
        if args.cmd == "providers":
            data = kb.get("/providers")
            for p in data["providers"]:
                flags = [
                    f
                    for f, on in (("default", p["default"]), ("unavailable", not p["available"]))
                    if on
                ]
                suffix = f" ({', '.join(flags)})" if flags else ""
                out.write(f"{p['name']:<10} {p['model'] or '-'}{suffix}\n")
            return EXIT_OK
        return repl(kb, Session(), inp, out, style)
    except ApiError as exc:
        (sys.stderr if out is sys.stdout else out).write(style.error(f"Error: {exc}") + "\n")
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_ERROR
    finally:
        if client is None:
            kb.close()
