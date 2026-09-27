"""JSON logging with a per-request id (set by the request middleware in app.main)."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
        }
        message = record.getMessage()
        # Messages that are already JSON objects (e.g. chat events) are merged, not nested.
        try:
            parsed = json.loads(message) if message.startswith("{") else None
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            entry.update(parsed)
        else:
            entry["message"] = message
        request_id = request_id_var.get()
        if request_id:
            entry["request_id"] = request_id
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Uvicorn's access log duplicates our request log line.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
    # httpx logs every Ollama request at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
