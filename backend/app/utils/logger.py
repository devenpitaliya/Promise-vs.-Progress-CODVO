"""Application logging: console + size-rotated, timestamped files with count and age retention.

Files are named `<prefix>_YYYY-MM-DD_HH-MM-SS.log` (the moment the file was started). When a file
reaches LOG_FILE_MAX_MB a new timestamped file begins; only the newest LOG_MAX_FILES are kept and
files older than LOG_RETENTION_DAYS are deleted. All of it is configured from `.env`.
"""

import contextvars
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(request_id)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
_CLEANUP_INTERVAL_SECONDS = 3600
_NOISY_LOGGERS = {"httpx": logging.WARNING, "httpcore": logging.WARNING, "chromadb": logging.WARNING, "apscheduler": logging.WARNING}


class RequestIdFilter(logging.Filter):
    """Adds the current request id (set by the HTTP middleware) to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class TimestampedRotatingFileHandler(logging.FileHandler):
    """Size-based rotation where every file is named after the time it was started."""

    def __init__(self, directory: Path, prefix: str, max_bytes: int, max_files: int, retention_days: int):
        self.directory = Path(directory)
        self.prefix = prefix
        self.max_bytes = max_bytes
        self.max_files = max_files
        self.retention_days = retention_days
        self._last_cleanup = 0.0
        self.directory.mkdir(parents=True, exist_ok=True)
        super().__init__(self._new_path(), encoding="utf-8", delay=False)
        self.cleanup()

    # -- naming -------------------------------------------------------------------------------
    def _new_path(self) -> str:
        stamp = datetime.now().strftime(TIMESTAMP_FORMAT)
        path = self.directory / f"{self.prefix}_{stamp}.log"
        counter = 1
        while path.exists():  # several rollovers within the same second
            path = self.directory / f"{self.prefix}_{stamp}_{counter}.log"
            counter += 1
        return str(path)

    def log_files(self) -> List[Path]:
        """This handler's files, oldest first (timestamped names sort chronologically)."""
        return sorted(self.directory.glob(f"{self.prefix}_*.log"), key=lambda p: (p.stat().st_mtime, p.name))

    # -- rotation -----------------------------------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.stream is not None:
                message = self.format(record) + self.terminator
                if self.stream.tell() + len(message.encode(self.encoding or "utf-8")) > self.max_bytes and self.stream.tell() > 0:
                    self.rollover()
            if time.monotonic() - self._last_cleanup > _CLEANUP_INTERVAL_SECONDS:
                self.cleanup()
            super().emit(record)
        except Exception:
            self.handleError(record)

    def rollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        self.baseFilename = os.path.abspath(self._new_path())
        self.stream = self._open()
        self.cleanup()

    def cleanup(self) -> None:
        """Delete files beyond LOG_MAX_FILES and files older than LOG_RETENTION_DAYS (never the active one)."""
        self._last_cleanup = time.monotonic()
        current = Path(self.baseFilename).resolve()
        files = [p for p in self.log_files() if p.resolve() != current]
        doomed = set()
        if self.retention_days > 0:
            cutoff = time.time() - self.retention_days * 86400
            doomed.update(p for p in files if p.stat().st_mtime < cutoff)
        keep_others = max(self.max_files - 1, 0)  # the active file counts towards the limit
        survivors = [p for p in files if p not in doomed]
        if len(survivors) > keep_others:
            doomed.update(survivors[: len(survivors) - keep_others])
        for path in doomed:
            try:
                path.unlink()
            except OSError:
                pass


_file_handler: Optional[TimestampedRotatingFileHandler] = None


def configure_logging(config) -> Optional[Path]:
    """Idempotently configure the root logger from settings. Returns the active log file, if any."""
    global _file_handler
    root = logging.getLogger()
    if any(getattr(h, "_app_handler", False) for h in root.handlers):
        return Path(_file_handler.baseFilename) if _file_handler else None

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    request_filter = RequestIdFilter()
    handlers: List[logging.Handler] = []

    if config.LOG_TO_CONSOLE:
        handlers.append(logging.StreamHandler(sys.stdout))
    if config.LOG_TO_FILE:
        _file_handler = TimestampedRotatingFileHandler(
            directory=config.log_dir,
            prefix=config.LOG_FILE_PREFIX,
            max_bytes=config.log_file_max_bytes,
            max_files=config.LOG_MAX_FILES,
            retention_days=config.LOG_RETENTION_DAYS,
        )
        handlers.append(_file_handler)

    for handler in handlers:
        handler._app_handler = True  # type: ignore[attr-defined]
        handler.setFormatter(formatter)
        handler.addFilter(request_filter)
        root.addHandler(handler)
    root.setLevel(config.LOG_LEVEL)

    # Route uvicorn's own logs into the same handlers; our middleware already logs each request.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    for name, level in _NOISY_LOGGERS.items():
        logging.getLogger(name).setLevel(max(level, logging.getLevelName(config.LOG_LEVEL)))

    return Path(_file_handler.baseFilename) if _file_handler else None
