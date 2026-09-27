"""scripts/start.py: free-port selection for the dev servers and the Docker stack."""

import importlib.util
import socket
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "start.py"


@pytest.fixture(scope="module")
def start() -> ModuleType:
    spec = importlib.util.spec_from_file_location("start_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["start_script"] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def listener() -> Iterator[int]:
    """A port that something listens on (like a server that is already running)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        yield sock.getsockname()[1]


def test_listening_port_is_busy(start: ModuleType, listener: int) -> None:
    assert start.accepts_connections(listener)
    assert not start.port_is_free(listener)


def test_busy_preferred_port_moves_to_the_next_free_one(start: ModuleType, listener: int) -> None:
    choice = start.choose("Backend", listener)
    assert choice.port > listener
    assert choice.moved
    assert start.port_is_free(choice.port)


def test_free_preferred_port_is_kept(start: ModuleType, listener: int) -> None:
    free = start.find_free_port(listener + 1)
    choice = start.choose("Backend", free)
    assert (choice.port, choice.moved) == (free, False)


def test_taken_ports_are_skipped(start: ModuleType, listener: int) -> None:
    free = start.find_free_port(listener + 1)
    assert start.find_free_port(free, taken={free}) > free


def test_own_container_port_is_reused_while_the_preferred_one_is_busy(
    start: ModuleType, listener: int
) -> None:
    assert start.choose("Web UI", listener, own=listener + 1).port == listener + 1


def test_own_container_moves_back_to_a_free_preferred_port(
    start: ModuleType, listener: int
) -> None:
    free = start.find_free_port(listener + 1)
    choice = start.choose("Web UI", free, own=free + 1)
    assert (choice.port, choice.moved) == (free, False)


def test_dotenv_reads_ports_and_ignores_comments(
    start: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = "# FRONTEND_PORT=1\nFRONTEND_PORT=9090 # web\nOLLAMA_PORT='11500'\n"
    (tmp_path / ".env").write_text(env_file)
    monkeypatch.setattr(start, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("FRONTEND_PORT", raising=False)
    monkeypatch.delenv("BACKEND_PORT", raising=False)
    monkeypatch.setenv("OLLAMA_PORT", "11600")
    assert start.int_setting("FRONTEND_PORT", 8080) == 9090
    assert start.int_setting("OLLAMA_PORT", 11434) == 11600  # the environment wins
    assert start.int_setting("BACKEND_PORT", 8000) == 8000
