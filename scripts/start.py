#!/usr/bin/env python3
"""Start the chatbot on free ports and print where to reach it.

A fixed port that is already taken stops the backend (uvicorn) or the Docker stack from
starting. This launcher checks each port first and, when it is busy, takes the next free one
(up to MAX_TRIES ports further). It then prints the URLs that are actually in use.

Usage:
  python3 scripts/start.py dev                   # backend (uvicorn --reload) + frontend (Vite)
  python3 scripts/start.py docker                # docker compose up -d --build
  python3 scripts/start.py docker --claude-only  # the same with docker-compose.claude-only.yml

Preferred ports come from the environment or the repo-root .env, else the defaults:
  dev:    BACKEND_PORT (8000), FRONTEND_DEV_PORT (5173)
  docker: FRONTEND_PORT (8080), OLLAMA_PORT (11434)

Standard library only.
"""

import argparse
import contextlib
import errno
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_TRIES = 50  # ports tried after the preferred one
DEFAULT_OLLAMA_URL = "http://localhost:11434"
READY_TIMEOUT_S = 120  # how long `dev` waits for both servers before printing the summary


# --- Port checks -------------------------------------------------------------


def accepts_connections(port: int) -> bool:
    """True when a server on this machine accepts connections on `port` (IPv4 or IPv6)."""
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            pass
    return False


def port_is_free(port: int) -> bool:
    """True when nothing listens on `port` (IPv4 or IPv6) and a server could bind it."""
    if accepts_connections(port):
        return False
    for family, host in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            continue  # no IPv6 on this machine
        with sock:
            if os.name != "nt":
                # Like uvicorn and Vite: ignore closed connections still in TIME_WAIT.
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            try:
                sock.bind((host, port))
            except OSError as exc:
                if exc.errno in (errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT):
                    continue  # the address family is unusable, not the port
                return False
    return True


def find_free_port(preferred: int, taken: set[int] | None = None) -> int:
    """The preferred port if it is free, else the next free one (skipping `taken`)."""
    for port in range(preferred, min(preferred + MAX_TRIES + 1, 65536)):
        if port not in (taken or set()) and port_is_free(port):
            return port
    sys.exit(f"No free port found in {preferred}-{preferred + MAX_TRIES}.")


@dataclass
class PortChoice:
    name: str
    preferred: int
    port: int

    @property
    def moved(self) -> bool:
        return self.port != self.preferred


def choose(
    name: str, preferred: int, own: int | None = None, taken: set[int] | None = None
) -> PortChoice:
    """Pick a port. `own` is the port this project's running container already publishes."""
    if own is not None and (own == preferred or not port_is_free(preferred)):
        return PortChoice(name, preferred, own)  # keep it; else move back to the preferred one
    return PortChoice(name, preferred, find_free_port(preferred, taken))


def report_ports(choices: list[PortChoice]) -> None:
    moved = [c for c in choices if c.moved]
    if not moved:
        return
    print("\nPort check:")
    for c in moved:
        print(f"  ! {c.name}: port {c.preferred} is already in use, using {c.port} instead")
    print()


# --- Settings ----------------------------------------------------------------


def dotenv() -> dict[str, str]:
    """KEY=VALUE pairs from the repo-root .env (no quoting or interpolation needed here)."""
    path = REPO_ROOT / ".env"
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.lstrip().startswith("#"):
                values[key.strip()] = value.split(" #")[0].strip().strip("\"'")
    return values


def setting(name: str, default: str) -> str:
    return os.environ.get(name) or dotenv().get(name) or default


def int_setting(name: str, default: int) -> int:
    value = setting(name, str(default))
    try:
        return int(value)
    except ValueError:
        sys.exit(f"{name}={value!r} is not a port number.")


def require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        sys.exit(f"'{tool}' was not found on PATH.")
    return path


# --- Docker Compose ----------------------------------------------------------


def compose_cmd(claude_only: bool) -> list[str]:
    cmd = [require("docker"), "compose", "-f", "docker-compose.yml"]
    if claude_only:
        cmd += ["-f", "docker-compose.claude-only.yml"]
    return cmd


def compose_port(service: str, container_port: int) -> int | None:
    """The host port that this project's running `service` publishes, if any."""
    if shutil.which("docker") is None:
        return None
    try:
        out = subprocess.run(
            ["docker", "compose", "port", service, str(container_port)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    host_port = out.stdout.strip().rpartition(":")[2]
    return int(host_port) if out.returncode == 0 and host_port.isdigit() else None


def run_docker(claude_only: bool) -> int:
    frontend = choose(
        "Web UI", int_setting("FRONTEND_PORT", 8080), own=compose_port("frontend", 80)
    )
    choices = [frontend]
    env = dict(os.environ, FRONTEND_PORT=str(frontend.port))
    if not claude_only:
        ollama = choose(
            "Ollama",
            int_setting("OLLAMA_PORT", 11434),
            own=compose_port("ollama", 11434),
            taken={frontend.port},
        )
        choices.append(ollama)
        env["OLLAMA_PORT"] = str(ollama.port)
    report_ports(choices)

    cmd = [*compose_cmd(claude_only), "up", "-d", "--build"]
    print("$ docker", " ".join(cmd[1:]), flush=True)
    code = subprocess.run(cmd, cwd=REPO_ROOT, env=env).returncode
    if code != 0:
        return code
    wait_for([frontend.port], [])  # nginx may need a moment after `up -d`

    url = f"http://localhost:{frontend.port}"
    lines = [
        ("Chat UI", url),
        ("Admin area", f"{url}/admin"),
        ("API health", f"{url}/api/v1/health"),
    ]
    if not claude_only:
        lines.append(("Ollama", f"http://127.0.0.1:{choices[1].port}"))
    lines.append(("CLI", f"cd backend && uv run python -m app.cli --url {url}"))
    summary("OmniCorp KB chatbot is running (Docker)", lines, choices)
    print("  Stop: docker compose down. Start again with scripts/start.py to re-check ports.\n")
    return 0


# --- Local development -------------------------------------------------------


def wait_for(ports: list[int], procs: list[subprocess.Popen[bytes]]) -> bool:
    """Wait until every port accepts connections; False if a process exits or time runs out."""
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if any(p.poll() is not None for p in procs):
            return False
        # Not a bind test: uvicorn --reload binds the port before its worker listens.
        if all(accepts_connections(port) for port in ports):
            return True
        time.sleep(0.5)
    return False


def signal_group(p: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    """Signal the process and, on POSIX, its whole group: npm starts Vite through a shell
    that doesn't pass signals on, and Vite may outlive npm."""
    if os.name == "nt":
        if p.poll() is None:
            p.kill() if sig == signal.SIGKILL else p.terminate()
        return
    with contextlib.suppress(ProcessLookupError):  # the group is already gone
        os.killpg(p.pid, sig)


def stop(procs: list[subprocess.Popen[bytes]]) -> None:
    for p in procs:
        signal_group(p, signal.SIGTERM)
    for p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            signal_group(p, signal.SIGKILL)


def interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def run_dev() -> int:
    # Ctrl+C and `kill` both stop the servers (they run in their own process groups).
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    uv, npm = require("uv"), require("npm")
    backend = choose("Backend", int_setting("BACKEND_PORT", 8000))
    frontend = choose("Frontend", int_setting("FRONTEND_DEV_PORT", 5173), taken={backend.port})
    choices = [backend, frontend]
    report_ports(choices)

    backend_url = f"http://localhost:{backend.port}"
    backend_env = dict(os.environ)
    # Ollama started by `scripts/start.py docker` may sit on another port than the default.
    ollama_port = compose_port("ollama", 11434)
    if ollama_port and setting("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL) == DEFAULT_OLLAMA_URL:
        backend_env["OLLAMA_BASE_URL"] = f"http://localhost:{ollama_port}"
    ollama_url = backend_env.get("OLLAMA_BASE_URL") or setting(
        "OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL
    )

    procs = [
        subprocess.Popen(
            [uv, "run", "uvicorn", "app.main:api", "--reload", "--port", str(backend.port)],
            cwd=REPO_ROOT / "backend",
            env=backend_env,
            start_new_session=True,  # own process group, stopped as a whole
        ),
        subprocess.Popen(
            [npm, "run", "dev", "--", "--port", str(frontend.port), "--strictPort"],
            cwd=REPO_ROOT / "frontend",
            env=dict(os.environ, API_PROXY_TARGET=backend_url),
            start_new_session=True,
        ),
    ]
    try:
        if wait_for([backend.port, frontend.port], procs):
            summary(
                "OmniCorp KB chatbot is running (local development)",
                [
                    ("Chat UI", f"http://localhost:{frontend.port}"),
                    ("Admin area", f"http://localhost:{frontend.port}/admin"),
                    ("Backend API", f"{backend_url}/api/v1/health"),
                    ("Swagger UI", f"{backend_url}/docs"),
                    ("Ollama", ollama_url),
                    ("CLI", f"cd backend && uv run python -m app.cli --url {backend_url}"),
                ],
                choices,
            )
            print("  Press Ctrl+C to stop both servers.\n", flush=True)
        # Run until a server exits (a crash, or Ctrl+C reaching both children).
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop(procs)
    failed = [
        p.returncode
        for p in procs
        if p.returncode not in (0, None, 130, 143, -signal.SIGINT, -signal.SIGTERM)
    ]
    return failed[0] if failed else 0


def summary(title: str, lines: list[tuple[str, str]], choices: list[PortChoice]) -> None:
    width = max(len(label) for label, _ in lines)
    print(f"\n{'=' * 72}\n  {title}\n{'-' * 72}")
    for label, value in lines:
        print(f"  {label.ljust(width)}  {value}")
    moved = [c for c in choices if c.moved]
    if moved:
        print(f"{'-' * 72}")
        for c in moved:
            print(f"  Note: {c.name} uses port {c.port} because {c.preferred} is already in use.")
    print("=" * 72, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("dev", help="run the backend and the Vite dev server locally")
    docker = sub.add_parser("docker", help="start the Docker Compose stack")
    docker.add_argument(
        "--claude-only", action="store_true", help="add docker-compose.claude-only.yml"
    )
    args = parser.parse_args()
    return run_dev() if args.mode == "dev" else run_docker(args.claude_only)


if __name__ == "__main__":
    sys.exit(main())
