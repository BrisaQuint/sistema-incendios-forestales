"""Bounded local diagnostics: deliberately exclude free-form messages and exceptions."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Mapping


class SafeOperationalFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Neither getMessage(), args, exc_info nor stack_info is serialized.
        source = "server" if record.name.startswith("uvicorn") else "application"
        return f"{self.formatTime(record)} {record.levelname} {source} diagnostic"


def configure_logging(values: Mapping[str, str]) -> RotatingFileHandler:
    def positive(name: str, default: int) -> int:
        try:
            value = int(values.get(name, str(default)))
            if value <= 0:
                raise ValueError
            return value
        except ValueError:
            raise ValueError(f"{name} must be a positive integer") from None

    size = positive("FIREWATCH_LOG_MAX_BYTES", 1_048_576)
    backups = positive("FIREWATCH_LOG_BACKUP_COUNT", 3)
    path = Path(values.get("FIREWATCH_LOG_PATH", "data/logs/firewatch.log"))
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=size, backupCount=backups, encoding="utf-8")
    handler.setFormatter(SafeOperationalFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    return handler
