#!/usr/bin/env python3
"""Add the knowledge-base MCP server (stdio) to Claude Desktop on this computer.

Run it on the computer where Claude Desktop is installed:

  # the repo is on this computer
  python3 scripts/install_claude_desktop_mcp.py

  # the repo runs on another machine (e.g. a VM): Claude Desktop starts the server over SSH
  ssh user@vm cat /path/to/repo/scripts/install_claude_desktop_mcp.py \\
    | python3 - --ssh user@vm --backend /path/to/repo/backend

It checks SSH without a password prompt (Claude Desktop cannot type one), backs up
claude_desktop_config.json and adds or replaces the server entry (other servers and Desktop's
own settings are kept), then starts the server exactly as Claude Desktop will and lists its
tools and prompts. Restart Claude Desktop afterwards. Standard library only.

It also installs three skills in ~/.claude/skills, so questions are one short command in
Claude Desktop's Code sessions and in Claude Code (their slash menus list skills, while
Desktop doesn't offer MCP prompts as commands):

  /kb <question>          the server's default model
  /kb-claude <question>   Claude writes the answer
  /kb-local <question>    the local Ollama model writes the answer
"""

import argparse
import json
import os
import platform
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

SSH_OPTS = ["-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30"]
# A non-interactive SSH session has a short PATH; uv usually lives in ~/.local/bin.
REMOTE_PATH = 'PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"'


def fail(message: str) -> None:
    print(f"\n[FAIL] {message}")
    sys.exit(1)


def default_config() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if system == "Windows":
        return Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def server_command(args: argparse.Namespace) -> tuple[str, list[str]]:
    run = ["run", "--quiet", "--directory", args.backend, "python", "-m", "app.mcp"]
    if args.ssh:
        remote = f"{REMOTE_PATH} uv " + " ".join(shlex.quote(part) for part in run)
        return shutil.which("ssh") or "ssh", [*SSH_OPTS, args.ssh, remote]
    uv = shutil.which("uv")
    if uv is None:
        fail("'uv' was not found on PATH; install it or use --ssh.")
    return str(uv), run


def check_server_machine(args: argparse.Namespace) -> None:
    probe = (
        f"{REMOTE_PATH} command -v uv >/dev/null && test -d {shlex.quote(args.backend)} && echo ok"
    )
    if not args.ssh:
        if not Path(args.backend, "app", "mcp").is_dir():
            fail(f"{args.backend} has no app/mcp: check out the dev-mcp branch there.")
        return
    if shutil.which("ssh") is None:
        fail("'ssh' was not found on this computer.")
    try:
        out = subprocess.run(
            ["ssh", *SSH_OPTS, args.ssh, probe], capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        fail(f"SSH to {args.ssh} timed out. Is the machine running?")
    if out.stdout.strip() != "ok":
        detail = out.stderr.strip() or f"uv or {args.backend} not found there"
        fail(
            f"SSH to {args.ssh} without a password prompt did not work:\n  {detail}\n"
            "  Claude Desktop cannot type a password: load your key (ssh-add) or run\n"
            f"  ssh-copy-id {args.ssh}, then run this again."
        )
    print(f"[ok] SSH to {args.ssh} works without a password prompt")


SKILLS = {
    "kb": ("the default model", "Leave out `model` (the server's default model answers).",
           "with its default model"),
    "kb-claude": ("Claude", 'Set `model` to "claude".', "and have Claude write the answer"),
    "kb-local": ("the local model", 'Set `model` to "local" (Ollama).',
                 "and have the local Ollama model write the answer"),
}  # fmt: skip

SKILL = """---
name: {name}
description: Ask the OmniCorp knowledge base ({server} MCP server) {purpose}. Answers strictly \
from OmniCorp's internal documentation, with citations. Use when the user types /{name} followed \
by a question.
argument-hint: <question>
---

Answer the question below with the `ask_knowledge_base` tool of the `{server}` MCP server, \
using {who}.

- Pass the question unchanged as `question`. {model_rule}
- Show the tool's `answer` as it is, then list the citations as "[n] title \u203a section (doc_id)".
- Say which model answered (the `model` field).
- If `refused` is true, say that the knowledge base doesn't cover the question. Don't answer \
from general knowledge.
- If the tool is not available or returns an error, say so and show the error; don't guess.

Question: $ARGUMENTS
"""


def install_skills(args: argparse.Namespace) -> None:
    root = Path(args.skills_dir).expanduser()
    for name, (who, model_rule, purpose) in SKILLS.items():
        path = root / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            SKILL.format(
                name=name, server=args.name, who=who, model_rule=model_rule, purpose=purpose
            ),
            encoding="utf-8",
        )
    print(f"[ok] Skills /{', /'.join(SKILLS)} in {root}")


def update_config(args: argparse.Namespace) -> Path:
    path = Path(args.config)
    cfg: dict[str, Any] = {}
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        try:
            cfg = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            fail(f"{path} is not valid JSON ({exc}). Fix or move it, then run this again.")
        backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
        print(f"[ok] Backup: {backup}")
    command, cmd_args = server_command(args)
    cfg.setdefault("mcpServers", {})[args.name] = {"command": command, "args": cmd_args}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] Updated {path} (servers: {', '.join(cfg['mcpServers'])})")
    for name, entry in cfg["mcpServers"].items():
        command = entry.get("command", "")
        if name != args.name and os.path.isabs(command) and not os.path.exists(command):
            print(f"[warn] Server '{name}': {command} does not exist on this computer")
    return path


def handshake(args: argparse.Namespace) -> None:
    """Start the server as Claude Desktop will and list what it offers."""
    command, cmd_args = server_command(args)
    proc = subprocess.Popen(
        [command, *cmd_args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdin, stdout, stderr = proc.stdin, proc.stdout, proc.stderr
    assert stdin and stdout and stderr
    lines: queue.Queue[str] = queue.Queue()
    errors: list[str] = []

    def read_stdout() -> None:
        for line in stdout:
            lines.put(line)

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=lambda: errors.extend(stderr), daemon=True).start()

    def send(message: dict[str, Any]) -> None:
        stdin.write(json.dumps(message) + "\n")
        stdin.flush()

    def reply(msg_id: int) -> dict[str, Any]:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                fail(f"The server wrote something that is not MCP to stdout: {line.strip()[:200]}")
            if message.get("id") == msg_id:
                return message.get("result", {})
        fail("No answer from the MCP server.\n" + "".join(errors[-10:]).strip())
        return {}

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "install-check", "version": "1"}}})  # fmt: skip
        name = reply(1)["serverInfo"]["name"]
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = [t["name"] for t in reply(2)["tools"]]
        send({"jsonrpc": "2.0", "id": 3, "method": "prompts/list"})
        prompts = [p["name"] for p in reply(3).get("prompts", [])]
        print(f"[ok] MCP handshake with '{name}'")
        print(f"     tools: {', '.join(tools)}")
        print(f"     prompts: {', '.join(prompts) or '-'}")
    finally:
        stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    script = Path(globals().get("__file__", "<stdin>"))
    piped = script.name == "<stdin>"  # `... | python3 -`: no repo next to the script
    repo_backend = None if piped else script.resolve().parent.parent / "backend"
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--ssh", metavar="USER@HOST", help="start the server on this machine over SSH"
    )
    parser.add_argument(
        "--backend", help="the repo's backend directory (on the SSH machine with --ssh)"
    )
    parser.add_argument("--name", default="omnicorp-kb", help="server name in Claude Desktop")
    parser.add_argument(
        "--config", default=str(default_config()), help="claude_desktop_config.json"
    )
    parser.add_argument(
        "--skills-dir", default="~/.claude/skills", help="where to put the /kb skills"
    )
    parser.add_argument("--no-skills", action="store_true", help="don't install the /kb skills")
    args = parser.parse_args()
    if args.backend is None:
        if args.ssh or repo_backend is None or not repo_backend.is_dir():
            parser.error("--backend is required with --ssh or when the script is piped in")
        args.backend = str(repo_backend)

    print(f"Adding '{args.name}' to Claude Desktop on {platform.node()}\n")
    check_server_machine(args)
    update_config(args)
    handshake(args)
    if not args.no_skills:
        install_skills(args)
    print("\nDone. Quit Claude Desktop completely and start it again.")


if __name__ == "__main__":
    main()
