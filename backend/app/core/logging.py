"""
Structured JSON logging with correlation IDs, request context, and log levels.
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Per-request correlation ID (set by middleware)
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

LEVEL_MAP = {
    "DEBUG":    logging.DEBUG,
    "INFO":     logging.INFO,
    "WARNING":  logging.WARNING,
    "ERROR":    logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class JSONFormatter(logging.Formatter):
    """Emit log records as structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        message: dict[str, Any] = {
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "level":          record.levelname,
            "logger":         record.name,
            "message":        record.getMessage(),
            "module":         record.module,
            "function":       record.funcName,
            "line":           record.lineno,
            "correlation_id": correlation_id_var.get(""),
        }

        # Extra fields attached via logger.info("msg", extra={...})
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
            ):
                message[key] = val

        if record.exc_info:
            message["exception"] = self.formatException(record.exc_info)

        return json.dumps(message, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable text format for local development."""

    COLORS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color  = self.COLORS.get(record.levelname, "")
        reset  = self.RESET
        ts     = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        cid    = correlation_id_var.get("")
        cid_str = f" [{cid[:8]}]" if cid else ""
        return (
            f"{color}{record.levelname:8}{reset} "
            f"\033[90m{ts}{reset}"
            f"{cid_str} "
            f"\033[97m{record.name}\033[0m — "
            f"{record.getMessage()}"
        )


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """
    Configure root logger. Call once at startup.
    fmt: "json" for production, "text" for development.
    """
    root = logging.getLogger()
    root.setLevel(LEVEL_MAP.get(level.upper(), logging.INFO))

    # Remove default handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter() if fmt == "json" else TextFormatter())
    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def set_correlation_id(cid: str | None = None) -> str:
    cid = cid or str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid
