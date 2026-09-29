"""Langfuse tracing that can never break the application.

`@observe(...)` is Langfuse's own decorator, applied only while tracing is active: with
LANGFUSE_ENABLED=false, missing keys, a missing `langfuse` package or a failed start-up the wrapped
function runs untouched. Every other helper here swallows and logs its own errors, so an outage or
misconfiguration of Langfuse costs a warning in the log, never a failed request.

What gets traced (see the decorated call sites):
  meeting-ingestion / review / reconciliation / briefing / pre-meeting-audit   traces (per user)
  commitment-extraction agent -> extraction chain -> llm-generation            spans and generations
  llm-generation                                                               model, parameters, tokens, cost, retries
  github / vector store / grounding tools                                     tool and retriever spans
"""

import asyncio
import contextlib
import functools
import inspect
import logging
from typing import Any, Callable, Dict, Iterator, List, Optional, TypeVar

from app.config import settings

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

try:  # the package is optional at runtime: without it tracing is simply off
    import langfuse as _langfuse_module
except Exception:  # pragma: no cover - depends on the environment
    _langfuse_module = None

_client: Any = None  # the Langfuse client while tracing is active
_project_id: Optional[str] = None  # resolved by the start-up check, used to build trace links
_off_reason: Optional[str] = "not started"


def off_reason() -> Optional[str]:
    """Why tracing is off (None while it is on)."""
    return None if _client is not None else _off_reason


def is_enabled() -> bool:
    return _client is not None


def init_tracing() -> Optional[str]:
    """Start the Langfuse client from settings. Returns why tracing is off, or None when it is on."""
    global _off_reason
    _off_reason = _start()
    return _off_reason


def _start() -> Optional[str]:
    global _client
    if _client is not None:
        return None
    if not settings.LANGFUSE_ENABLED:
        return "disabled (LANGFUSE_ENABLED=false)"
    if _langfuse_module is None:
        return "the 'langfuse' package is not installed"
    if not settings.langfuse_configured:
        return "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required"
    try:
        _client = _langfuse_module.Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            base_url=settings.LANGFUSE_BASE_URL,
            environment=settings.langfuse_environment,
            release=settings.LANGFUSE_RELEASE,
            sample_rate=settings.LANGFUSE_SAMPLE_RATE,
            flush_at=settings.LANGFUSE_FLUSH_AT,
            flush_interval=settings.LANGFUSE_FLUSH_INTERVAL_SECONDS,
            timeout=settings.LANGFUSE_TIMEOUT_SECONDS,
            debug=settings.LANGFUSE_DEBUG,
        )
    except Exception as exc:
        _client = None
        logger.warning("Langfuse could not start, tracing is off: %s", exc.__class__.__name__)
        return f"client failed to start ({exc.__class__.__name__})"
    logger.info(
        "Langfuse tracing on: %s (environment=%s, sample_rate=%s)",
        settings.LANGFUSE_BASE_URL,
        settings.langfuse_environment,
        settings.LANGFUSE_SAMPLE_RATE,
    )
    return None


def shutdown_tracing() -> None:
    """Flush pending traces and stop the exporter (application shutdown)."""
    global _client, _off_reason
    if _client is None:
        return
    _off_reason = "shut down"
    try:
        _client.shutdown()
    except Exception as exc:
        logger.warning("Langfuse shutdown failed: %s", exc.__class__.__name__)
    _client = None


def verify_connection() -> bool:
    """Blocking check that the keys are accepted; also resolves the project id for trace links."""
    global _project_id
    if _client is None:
        return False
    if not _client.auth_check():
        return False
    with contextlib.suppress(Exception):
        projects = _client.api.projects.get()
        _project_id = projects.data[0].id if projects.data else None
    return True


def _safe(action: str, call: Callable[[], Any]) -> Any:
    if _client is None:
        return None
    try:
        return call()
    except Exception as exc:
        logger.debug("Langfuse %s failed: %s", action, exc)
        return None


def observe(
    name: Optional[str] = None, *, as_type: str = "span", capture_input: bool = False, capture_output: bool = False
) -> Callable[[F], F]:
    """Langfuse's `@observe`, active only while tracing is on.

    Arguments are captured only when both the call site asks for it and LANGFUSE_CAPTURE_CONTENT=true.
    `capture_input`/`capture_output` default to False because most arguments are ORM objects and sessions.
    """

    def decorator(func: F) -> F:
        if _langfuse_module is None:
            return func
        traced = _langfuse_module.observe(
            func,
            name=name or func.__name__,
            as_type=as_type,  # type: ignore[arg-type]
            capture_input=capture_input and settings.LANGFUSE_CAPTURE_CONTENT,
            capture_output=capture_output and settings.LANGFUSE_CAPTURE_CONTENT,
        )

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await (traced if _client is not None else func)(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return (traced if _client is not None else func)(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


@contextlib.contextmanager
def trace_attributes(
    *,
    user_id: Optional[int] = None,
    session_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    version: Optional[str] = None,
    name: Optional[str] = None,
) -> Iterator[None]:
    """Attach user, session, tags and metadata to every observation created inside the block."""
    manager = None
    if _client is not None and _langfuse_module is not None:
        try:
            manager = _langfuse_module.propagate_attributes(
                user_id=str(user_id) if user_id is not None else None,
                session_id=session_id,
                tags=tags,
                # Langfuse only accepts short string metadata values on propagated attributes.
                metadata={k: str(v)[:200] for k, v in {"request_id": _request_id(), **(metadata or {})}.items() if v not in (None, "-")},
                version=version,
                trace_name=name,
            )
            manager.__enter__()
        except Exception as exc:
            logger.debug("Langfuse attributes failed: %s", exc)
            manager = None
    try:
        yield
    finally:
        if manager is not None:
            with contextlib.suppress(Exception):
                manager.__exit__(None, None, None)


def _request_id() -> Optional[str]:
    from app.utils.logger import request_id_var  # local import: logger imports settings only

    return request_id_var.get()


def content(value: Any) -> Any:
    """`value` when content capture is on, otherwise None (prompts and transcripts stay private)."""
    return value if settings.LANGFUSE_CAPTURE_CONTENT else None


def update_span(**fields: Any) -> None:
    _safe("span update", lambda: _client.update_current_span(**{k: v for k, v in fields.items() if v is not None}))


def cost_of(model: str, input_tokens: int, output_tokens: int) -> Optional[Dict[str, float]]:
    """USD cost from LLM_PRICING; None lets Langfuse price models it knows itself."""
    rates = settings.llm_pricing.get(model)
    if rates is None:
        return None
    input_cost = input_tokens * rates[0] / 1_000_000
    output_cost = output_tokens * rates[1] / 1_000_000
    return {"input": round(input_cost, 8), "output": round(output_cost, 8), "total": round(input_cost + output_cost, 8)}


def record_usage(model: str, input_tokens: Optional[int], output_tokens: Optional[int], **metadata: Any) -> None:
    """Report token usage (and cost when priced) on the current LLM generation."""
    if _client is None or input_tokens is None:
        return
    output_tokens = output_tokens or 0
    logger.debug("LLM usage %s: %s input + %s output tokens", model, input_tokens, output_tokens)
    usage = {"input": input_tokens, "output": output_tokens, "total": input_tokens + output_tokens}
    _safe(
        "usage update",
        lambda: _client.update_current_generation(
            model=model,
            usage_details=usage,
            cost_details=cost_of(model, input_tokens, output_tokens),
            metadata={k: v for k, v in metadata.items() if v is not None} or None,
        ),
    )


def update_generation(**fields: Any) -> None:
    _safe("generation update", lambda: _client.update_current_generation(**{k: v for k, v in fields.items() if v is not None}))


def current_trace_id() -> Optional[str]:
    return _safe("trace id", lambda: _client.get_current_trace_id())


def trace_url(trace_id: Optional[str]) -> Optional[str]:
    if not trace_id or not _project_id or _client is None:
        return None
    return f"{settings.LANGFUSE_BASE_URL.rstrip('/')}/project/{_project_id}/traces/{trace_id}"


async def flush() -> None:
    """Send buffered traces now (used by short-lived jobs such as scheduled audits)."""
    if _client is not None:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_client.flush)
