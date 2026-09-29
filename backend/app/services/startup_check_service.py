"""Startup diagnostics: probe every dependency before serving traffic and log each result.

Status meanings:
  OK       working as configured
  WARN     degraded but the app can run (e.g. bad GitHub token -> sync failures)
  FAIL     the app cannot run (database); startup is aborted
  SKIPPED  not configured or disabled in `.env`
Secrets are never logged.
"""

import asyncio
import logging
import smtplib
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, List

import httpx
from sqlalchemy import text

from app.config import INSECURE_SECRET_PLACEHOLDER, settings
from app.constants.github import GITHUB_API_VERSION, GITHUB_USER_AGENT
from app.database.migrations import head_revision
from app.database.session import engine
from app.enums import LLMProvider
from app.llms import test_api_key
from app.llms.factory import fallback_model_for
from app.services.connectors import build, is_available
from app.services.scheduler_service import scheduler_service
from app.services.vector_store_service import vector_store
from app.utils import tracing

logger = logging.getLogger("app.startup")

OK, WARN, FAIL, SKIPPED = "OK", "WARN", "FAIL", "SKIPPED"


class StartupCheckError(RuntimeError):
    pass


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    duration_ms: float = 0.0


async def _timed(name: str, probe: Callable[[], Awaitable[CheckResult]]) -> CheckResult:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(probe(), timeout=settings.STARTUP_CHECK_TIMEOUT_SECONDS)
    except TimeoutError:
        result = CheckResult(name, WARN if name != "database" else FAIL, f"no answer within {settings.STARTUP_CHECK_TIMEOUT_SECONDS:.0f}s")
    except Exception as exc:  # a probe must never crash startup by itself
        result = CheckResult(name, WARN if name != "database" else FAIL, f"{exc.__class__.__name__}: {exc}"[:300])
    result.duration_ms = (time.perf_counter() - started) * 1000
    return result


# ---- individual checks -------------------------------------------------------------------
async def check_configuration() -> CheckResult:
    detail = (
        f"environment={settings.ENVIRONMENT}, listen={settings.APP_HOST}:{settings.APP_PORT}, api={settings.API_PREFIX}, "
        f"frontend={settings.FRONTEND_URL}, cors={len(settings.allowed_origins)} origin(s), timezone={settings.APP_TIMEZONE}, "
        f"data_dir={settings.data_dir}, logs={settings.log_dir} (max {settings.LOG_MAX_FILES} x {settings.LOG_FILE_MAX_MB:g} MB, "
        f"{settings.LOG_RETENTION_DAYS} day retention)"
    )
    if settings.SECRET_KEY == INSECURE_SECRET_PLACEHOLDER:
        return CheckResult("configuration", WARN, f"SECRET_KEY is the placeholder value; set a random one. {detail}")
    return CheckResult("configuration", OK, detail)


async def check_database() -> CheckResult:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        dialect = conn.dialect.name
        version = ".".join(str(part) for part in (conn.dialect.server_version_info or ())) or "unknown"

        def current_revision(sync_conn):
            from alembic.runtime.migration import MigrationContext

            return MigrationContext.configure(sync_conn).get_current_revision()

        current = await conn.run_sync(current_revision)
    head = await asyncio.to_thread(head_revision)
    detail = f"{dialect} {version}, schema revision {current or 'none'} (head {head})"
    return CheckResult("database", OK if current == head else WARN, detail if current == head else f"schema not at head: {detail}")


async def check_llm() -> List[CheckResult]:
    configured = {
        LLMProvider.GEMINI: (settings.GEMINI_API_KEY, settings.GEMINI_MODEL),
        LLMProvider.OPENAI: (settings.OPENAI_API_KEY, settings.OPENAI_MODEL),
    }
    results = []
    for provider, (key, model) in configured.items():
        name = f"llm:{provider}"
        if not key:
            results.append(CheckResult(name, SKIPPED, "no server key (users may add their own in Settings)"))
        elif not settings.STARTUP_CHECK_LLM:
            results.append(CheckResult(name, OK, f"key configured, model {model} (live probe disabled)"))
        else:

            async def probe(provider=provider, key=key, name=name, model=None) -> CheckResult:
                valid, message = await test_api_key(provider, key, model)
                return CheckResult(name, OK if valid else WARN, message)

            results.append(await _timed(name, probe))
            fallback = fallback_model_for(provider)
            if fallback and fallback != model:
                fallback_name = f"{name}:fallback"
                results.append(await _timed(fallback_name, lambda p=probe, n=fallback_name, m=fallback: p(name=n, model=m)))
    if not any(r.status == OK for r in results):
        results.append(CheckResult("llm", OK, f"extraction falls back to the rule-based parser; temperature={settings.LLM_TEMPERATURE}"))
    return results


async def check_github() -> CheckResult:
    if not settings.GITHUB_PERSONAL_ACCESS_TOKEN:
        return CheckResult("github", SKIPPED, "no token: simulation mode, clearly labelled in the UI")
    if not settings.STARTUP_CHECK_GITHUB:
        return CheckResult("github", OK, "token configured (live probe disabled)")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.GITHUB_PERSONAL_ACCESS_TOKEN}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": GITHUB_USER_AGENT,
    }
    async with httpx.AsyncClient(base_url=settings.GITHUB_API_URL, headers=headers, timeout=settings.GITHUB_TIMEOUT_SECONDS) as client:
        response = await client.get("/user")
    if response.status_code != 200:
        return CheckResult("github", WARN, f"{settings.GITHUB_API_URL} rejected the token (HTTP {response.status_code}); syncs will fail")
    login = response.json().get("login", "?")
    remaining = response.headers.get("x-ratelimit-remaining", "?")
    owner = settings.GITHUB_DEFAULT_OWNER or "not set (repositories must be owner/repo)"
    return CheckResult("github", OK, f"authenticated as {login}, rate limit remaining {remaining}, default owner {owner}")


async def check_smtp() -> CheckResult:
    if not settings.smtp_configured:
        return CheckResult("smtp", SKIPPED, "not configured: briefings are saved to history but not sent")
    if not settings.STARTUP_CHECK_SMTP:
        return CheckResult("smtp", OK, f"{settings.SMTP_HOST}:{settings.SMTP_PORT} configured (live probe disabled)")

    def login() -> None:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS) as server:
            if settings.SMTP_STARTTLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

    try:
        await asyncio.to_thread(login)
    except (smtplib.SMTPException, OSError) as exc:
        return CheckResult(
            "smtp", WARN, f"{settings.SMTP_HOST}:{settings.SMTP_PORT} login failed ({exc.__class__.__name__}); emails will fail"
        )
    return CheckResult("smtp", OK, f"logged in to {settings.SMTP_HOST}:{settings.SMTP_PORT} as sender {settings.SMTP_FROM_EMAIL}")


async def check_vector_store() -> CheckResult:
    if not settings.SEMANTIC_SEARCH_ENABLED:
        return CheckResult("vector_store", SKIPPED, "semantic search disabled")
    count = await vector_store.health()
    if count is None:
        return CheckResult("vector_store", WARN, "could not open the Chroma store; semantic search unavailable")
    return CheckResult(
        "vector_store", OK, f"{count} commitment(s) indexed, embeddings={settings.EMBEDDING_PROVIDER}, path={settings.chroma_dir}"
    )


async def check_scheduler() -> CheckResult:
    if not settings.ENABLE_SCHEDULER:
        return CheckResult("scheduler", SKIPPED, "disabled on this instance (ENABLE_SCHEDULER=false)")
    if not scheduler_service.running:
        return CheckResult("scheduler", WARN, "not running; scheduled audits will not fire")
    jobs = len(scheduler_service.scheduler.get_jobs())
    return CheckResult("scheduler", OK, f"running, {jobs} job(s), GitHub re-check every {settings.VERIFICATION_INTERVAL_MINUTES} min")


async def check_jira() -> CheckResult:
    if not is_available("jira"):
        return CheckResult("jira", SKIPPED, "coming soon (not in ENABLED_INTEGRATIONS)")
    connector = build("jira")
    if not connector.is_configured():
        return CheckResult("jira", SKIPPED, "no server default: users connect their own in Settings, else Jira is simulated")
    result = await connector.test()
    return CheckResult("jira", OK if result.ok else WARN, result.message)


async def check_slack() -> CheckResult:
    if not is_available("slack"):
        return CheckResult("slack", SKIPPED, "coming soon (not in ENABLED_INTEGRATIONS)")
    connector = build("slack")
    if not connector.is_configured():
        return CheckResult("slack", SKIPPED, "no server default: users connect their own in Settings")
    # No live probe: the only reliable Slack check posts a message, which must not happen on every restart.
    return CheckResult("slack", OK, f"server default configured for {connector.target} (test it from Settings)")


async def check_langfuse() -> CheckResult:
    reason = tracing.off_reason()
    if reason is not None:
        status = WARN if settings.LANGFUSE_ENABLED else SKIPPED
        return CheckResult("langfuse", status, f"tracing off: {reason}")
    if not settings.STARTUP_CHECK_LANGFUSE:
        return CheckResult("langfuse", OK, f"tracing to {settings.LANGFUSE_BASE_URL} (live probe disabled)")
    try:
        accepted = await asyncio.to_thread(tracing.verify_connection)
    except Exception as exc:
        return CheckResult(
            "langfuse", WARN, f"{settings.LANGFUSE_BASE_URL} unreachable ({exc.__class__.__name__}); traces are buffered and may be dropped"
        )
    if not accepted:
        return CheckResult("langfuse", WARN, f"{settings.LANGFUSE_BASE_URL} rejected the keys; traces will not be stored")
    detail = (
        f"tracing to {settings.LANGFUSE_BASE_URL}, environment={settings.langfuse_environment}, sample_rate={settings.LANGFUSE_SAMPLE_RATE}"
    )
    return CheckResult("langfuse", OK, detail + ("" if settings.LANGFUSE_CAPTURE_CONTENT else ", content capture off"))


# ---- runner ------------------------------------------------------------------------------
def _log(result: CheckResult) -> None:
    level = {OK: logging.INFO, SKIPPED: logging.INFO, WARN: logging.WARNING, FAIL: logging.ERROR}[result.status]
    logger.log(level, "[%-7s] %-14s %s (%.0f ms)", result.status, result.name, result.detail, result.duration_ms)


async def run_startup_checks() -> List[CheckResult]:
    """Run all checks, log each one and a summary. Raises StartupCheckError when the app must not start."""
    if not settings.STARTUP_CHECKS_ENABLED:
        logger.info("Startup checks disabled (STARTUP_CHECKS_ENABLED=false)")
        return []

    logger.info("Running startup checks...")
    results = [await _timed("configuration", check_configuration), await _timed("database", check_database)]
    for result in results:
        _log(result)

    parallel = await asyncio.gather(
        check_llm(),
        _timed("github", check_github),
        _timed("smtp", check_smtp),
        _timed("vector_store", check_vector_store),
        _timed("scheduler", check_scheduler),
        _timed("langfuse", check_langfuse),
        _timed("jira", check_jira),
        _timed("slack", check_slack),
    )
    for item in parallel:
        for result in item if isinstance(item, list) else [item]:
            _log(result)
            results.append(result)

    counts = {status: sum(r.status == status for r in results) for status in (OK, WARN, FAIL, SKIPPED)}
    summary = ", ".join(f"{n} {s.lower()}" for s, n in counts.items())
    failed = [r.name for r in results if r.status == FAIL]
    warned = [r.name for r in results if r.status == WARN]

    if failed or (warned and settings.STARTUP_FAIL_ON_WARNING):
        logger.error("Startup checks failed (%s): %s", summary, ", ".join(failed + warned))
        raise StartupCheckError(f"Startup checks failed: {', '.join(failed + warned)}")
    logger.log(logging.WARNING if warned else logging.INFO, "Startup checks complete: %s", summary)
    return results
