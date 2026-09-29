import asyncio
import logging
import os
import re
import time

import pytest
from alembic import command

from app.config import settings
from app.database.migrations import alembic_config
from app.services import startup_check_service
from app.services.startup_check_service import FAIL, OK, SKIPPED, WARN, CheckResult, StartupCheckError, run_startup_checks
from app.utils.logger import RequestIdFilter, TimestampedRotatingFileHandler, request_id_var

NAME = re.compile(r"^app_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(_\d+)?\.log$")


def make_handler(tmp_path, max_bytes=200, max_files=6, retention_days=7):
    handler = TimestampedRotatingFileHandler(tmp_path, "app", max_bytes=max_bytes, max_files=max_files, retention_days=retention_days)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def emit(handler, message="x" * 60):
    handler.emit(logging.LogRecord("t", logging.INFO, __file__, 1, message, None, None))


def test_files_are_named_with_start_date_and_time(tmp_path):
    handler = make_handler(tmp_path)
    emit(handler)
    handler.close()
    [path] = list(tmp_path.iterdir())
    assert NAME.match(path.name), path.name


def test_rotates_at_max_size_and_keeps_max_files(tmp_path):
    handler = make_handler(tmp_path, max_bytes=200, max_files=6)
    for _ in range(100):  # ~6 KB of logs -> many rollovers
        emit(handler)
    handler.close()
    files = list(tmp_path.glob("app_*.log"))
    assert len(files) == 6
    assert all(f.stat().st_size <= 200 for f in files)
    assert all(NAME.match(f.name) for f in files)


def test_deletes_files_older_than_retention(tmp_path):
    old = tmp_path / "app_2020-01-01_00-00-00.log"
    old.write_text("old")
    ten_days_ago = time.time() - 10 * 86400
    os.utime(old, (ten_days_ago, ten_days_ago))
    unrelated = tmp_path / "other.log"
    unrelated.write_text("not ours")

    handler = make_handler(tmp_path, retention_days=7)
    handler.close()
    assert not old.exists()
    assert unrelated.exists()  # only files with our prefix are managed


def test_retention_zero_keeps_old_files_by_count_only(tmp_path):
    old = tmp_path / "app_2020-01-01_00-00-00.log"
    old.write_text("old")
    os.utime(old, (0, 0))
    make_handler(tmp_path, retention_days=0).close()
    assert old.exists()


def test_request_id_is_attached_to_records():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
    token = request_id_var.set("abc123")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)
    assert record.request_id == "abc123"


async def test_startup_checks_pass_and_skip_unconfigured_integrations(caplog):
    await asyncio.to_thread(command.stamp, alembic_config(), "head")  # test schema comes from create_all
    caplog.set_level(logging.INFO, logger="app.startup")
    results = {r.name: r for r in await run_startup_checks()}
    assert results["database"].status == OK
    assert results["github"].status == SKIPPED  # no token -> simulation mode
    assert results["smtp"].status == SKIPPED
    assert "Startup checks complete" in caplog.text
    assert settings.SECRET_KEY not in caplog.text


async def test_database_failure_aborts_startup(monkeypatch):
    async def broken():
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(startup_check_service, "check_database", broken)
    with pytest.raises(StartupCheckError, match="database"):
        await run_startup_checks()


async def test_warnings_abort_only_when_configured(monkeypatch):
    async def flaky():
        return CheckResult("github", WARN, "token rejected")

    monkeypatch.setattr(startup_check_service, "check_github", flaky)
    results = await run_startup_checks()
    assert any(r.status == WARN for r in results)

    monkeypatch.setattr(settings, "STARTUP_FAIL_ON_WARNING", True)
    with pytest.raises(StartupCheckError, match="github"):
        await run_startup_checks()


async def test_checks_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "STARTUP_CHECKS_ENABLED", False)
    assert await run_startup_checks() == []


def test_statuses_are_distinct():
    assert len({OK, WARN, FAIL, SKIPPED}) == 4
