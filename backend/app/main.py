import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database.migrations import head_revision, upgrade_to_head
from app.database.session import engine
from app.routers.api import api_router
from app.services.scheduler_service import scheduler_service
from app.services.startup_check_service import run_startup_checks
from app.utils import tracing
from app.utils.exceptions import AppError
from app.utils.logger import configure_logging, request_id_var

LOG_FILE = configure_logging(settings)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    started = time.perf_counter()
    logger.info("=" * 72)
    logger.info("Starting %s v%s (environment=%s)", settings.APP_NAME, app.version, settings.ENVIRONMENT)
    logger.info("Log file: %s", LOG_FILE or "disabled (LOG_TO_FILE=false)")
    try:
        if settings.RUN_MIGRATIONS_ON_STARTUP:
            await asyncio.to_thread(upgrade_to_head)
            logger.info("Database migrations applied (head %s)", await asyncio.to_thread(head_revision))
        if settings.ENABLE_SCHEDULER:
            await scheduler_service.start()
        tracing.init_tracing()
        await run_startup_checks()
    except Exception:
        logger.critical("Startup aborted", exc_info=True)
        scheduler_service.shutdown()
        tracing.shutdown_tracing()
        await engine.dispose()
        raise
    logger.info(
        "%s is ready on http://%s:%s%s (github=%s, demo_mode=%s) in %.1fs",
        settings.APP_NAME,
        settings.APP_HOST,
        settings.APP_PORT,
        settings.API_PREFIX,
        settings.github_mode,
        settings.DEMO_MODE,
        time.perf_counter() - started,
    )
    yield
    logger.info("Shutting down %s", settings.APP_NAME)
    scheduler_service.shutdown()
    await asyncio.to_thread(tracing.shutdown_tracing)  # flushes buffered traces
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="Closed-loop tracking of meeting commitments against GitHub delivery.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = (request.headers.get("X-Request-ID") or uuid.uuid4().hex)[:64]
    token = request_id_var.set(request_id)  # every log line of this request carries the id
    started = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith(settings.API_PREFIX):
            response.headers["Cache-Control"] = "no-store"
            level = logging.ERROR if response.status_code >= 500 else logging.WARNING if response.status_code >= 400 else logging.INFO
            client = request.client.host if request.client else "-"
            logger.log(level, "%s %s -> %s (%.0f ms) client=%s", request.method, request.url.path, response.status_code, elapsed_ms, client)
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(AppError)
async def domain_error(_: Request, exc: AppError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(api_router)


@app.get("/health", tags=["System"])
async def health() -> dict:
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/ready", tags=["System"])
async def ready() -> JSONResponse:
    """Readiness: the database answers."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(content={"status": "ready"})
