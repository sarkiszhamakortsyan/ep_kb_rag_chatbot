"""Choosing the model by typing, as in the web chat: `/claude`, `/local`, `/ministral`, ...

The command names are the provider name, a short name and the model family. They are built
from `GET /providers`, so only the enabled models are offered.
"""

import re
from dataclasses import dataclass
from typing import Any

SHORT_NAMES = {"anthropic": "claude", "ollama": "local"}
# A command word; "/v3/records:batch ..." and other paths are questions, not commands.
COMMAND = re.compile(r"^/([a-z][a-z0-9.-]*)(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
NAME = re.compile(r"^[a-z][a-z0-9.-]*$")


@dataclass(frozen=True)
class ModelCommand:
    name: str
    provider: dict[str, Any]  # an entry of GET /providers


def model_commands(providers: list[dict[str, Any]]) -> dict[str, ModelCommand]:
    """Command name -> provider, e.g. {"claude": anthropic, "anthropic": anthropic, ...}."""
    commands: dict[str, ModelCommand] = {}
    for provider in providers:
        family = re.split(r"[-:]", provider.get("model") or "")[0].lower()
        for name in (SHORT_NAMES.get(provider["name"]), provider["name"], family):
            if name and NAME.match(name) and name not in commands:
                commands[name] = ModelCommand(name, provider)
    return commands


def split_command(text: str) -> tuple[str, str] | None:
    """("claude", "the question") for "/claude the question"; None if it is not a command."""
    match = COMMAND.match(text.strip())
    if not match:
        return None
    return match.group(1).lower(), (match.group(2) or "").strip()


def label(provider: dict[str, Any]) -> str:
    return f"{provider['name']} ({provider.get('model') or '-'})"


def model_list(commands: dict[str, ModelCommand], selected: str | None) -> str:
    by_provider: dict[str, list[str]] = {}
    providers: dict[str, dict[str, Any]] = {}
    for command in commands.values():
        name = command.provider["name"]
        by_provider.setdefault(name, []).append(f"/{command.name}")
        providers[name] = command.provider
    lines = []
    for name, names in by_provider.items():
        provider = providers[name]
        state = "" if provider.get("available", True) else " (unavailable)"
        if name == selected or (selected is None and provider.get("default")):
            state += " (selected)"
        lines.append(f"  {label(provider)}: {', '.join(names)}{state}")
    return "Models:\n" + "\n".join(lines)
