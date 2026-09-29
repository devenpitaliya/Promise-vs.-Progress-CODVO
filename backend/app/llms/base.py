import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.config import settings
from app.enums import LLMProvider
from app.utils import tracing
from app.utils.tracing import observe

logger = logging.getLogger(__name__)

# Provider responses worth retrying: rate limited or temporarily overloaded.
TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

# (provider, model) -> monotonic time until which the model is skipped (its quota is exhausted).
_model_cooldowns: dict[tuple[str, str], float] = {}


def reset_model_cooldowns() -> None:
    _model_cooldowns.clear()


class LLMError(RuntimeError):
    """Any provider failure: network, timeout, refusal or non-JSON output."""


class _TransientExhausted(Exception):
    """A model kept returning temporary errors after all retries (internal: triggers the fallback model)."""


@dataclass(frozen=True)
class LLMCredentials:
    provider: LLMProvider
    api_key: str
    model: str
    # Tried when `model` keeps failing with temporary errors (overloaded / rate limited).
    fallback_model: Optional[str] = None


@dataclass(frozen=True)
class GenerationOptions:
    """Per-call knobs; defaults come from the environment (see app/config/settings.py)."""

    temperature: float = settings.LLM_TEMPERATURE
    max_output_tokens: int = settings.LLM_MAX_OUTPUT_TOKENS
    timeout_seconds: float = settings.LLM_TIMEOUT_SECONDS


class LLMClient(ABC):
    """Provider-agnostic JSON generation. Chains and agents depend on this, never on an SDK."""

    def __init__(self, credentials: LLMCredentials):
        self.credentials = credentials
        self.last_model: Optional[str] = None  # model that produced the most recent answer

    @property
    def provider(self) -> LLMProvider:
        return self.credentials.provider

    @abstractmethod
    async def _complete(self, system_prompt: str, user_prompt: str, options: GenerationOptions, model: str) -> str:
        """Return the raw text of a JSON-mode completion."""

    @observe("llm-generation", as_type="generation")
    async def _traced_complete(self, system_prompt: str, user_prompt: str, options: GenerationOptions, model: str) -> str:
        """One provider call, recorded in Langfuse with model, parameters, tokens, cost and errors."""
        tracing.update_generation(
            model=model,
            model_parameters={"temperature": options.temperature, "max_output_tokens": options.max_output_tokens},
            input=tracing.content([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]),
            metadata={"provider": str(self.provider)},
        )
        text = await self._complete(system_prompt, user_prompt, options, model)
        tracing.update_generation(output=tracing.content(text))
        return text

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        return code if isinstance(code, int) else None

    async def _complete_with_retries(self, system_prompt: str, user_prompt: str, options: GenerationOptions, model: str) -> str:
        """One model, with exponential backoff on temporary errors. Permanent errors raise LLMError at once."""
        attempts = settings.LLM_TRANSIENT_RETRIES + 1
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.wait_for(
                    self._traced_complete(system_prompt, user_prompt, options, model), timeout=options.timeout_seconds
                )
            except TimeoutError as exc:
                raise LLMError(f"{self.provider} timed out after {options.timeout_seconds:.0f}s") from exc
            except LLMError:
                raise
            except Exception as exc:  # provider SDKs raise many exception types
                if self._status_code(exc) not in TRANSIENT_STATUS_CODES:
                    raise LLMError(f"{self.provider} request failed: {self._describe(exc)}") from exc
                if self._is_quota_exhausted(exc):
                    # A spent quota will not recover within seconds: skip retries and cool the model down.
                    _model_cooldowns[(self.provider, model)] = time.monotonic() + settings.LLM_MODEL_COOLDOWN_SECONDS
                    raise _TransientExhausted(self._describe(exc)) from exc
                if attempt == attempts:
                    raise _TransientExhausted(self._describe(exc)) from exc
                delay = settings.LLM_RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1)
                logger.warning(
                    "%s %s transient error (attempt %s/%s, retrying in %.1fs): %s",
                    self.provider,
                    model,
                    attempt,
                    attempts,
                    delay,
                    self._describe(exc),
                )
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    def _is_quota_exhausted(self, exc: Exception) -> bool:
        message = str(getattr(exc, "message", None) or exc).lower()
        return self._status_code(exc) == 429 and "quota" in message

    def _describe(self, exc: Exception) -> str:
        """Status code + provider message, trimmed and with the API key redacted, for logs and the UI."""
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        message = str(getattr(exc, "message", None) or exc).replace(self.credentials.api_key, "***").strip()
        message = " ".join(message.split())[:200]
        parts = [exc.__class__.__name__] + ([f"HTTP {code}"] if code else []) + ([message] if message else [])
        return " - ".join(parts)

    @observe("llm-call")
    async def generate_json(self, system_prompt: str, user_prompt: str, options: GenerationOptions | None = None) -> Dict[str, Any]:
        options = options or GenerationOptions()
        models = [self.credentials.model]
        if self.credentials.fallback_model and self.credentials.fallback_model != self.credentials.model:
            models.append(self.credentials.fallback_model)

        now = time.monotonic()
        available = [m for m in models if _model_cooldowns.get((self.provider, m), 0) <= now]
        if len(available) < len(models):
            logger.info("%s skipping %s (quota exhausted, cooling down)", self.provider, ", ".join(m for m in models if m not in available))
        models = available or models[-1:]  # always try at least the last-resort model

        text = ""
        for index, model in enumerate(models):
            try:
                text = await self._complete_with_retries(system_prompt, user_prompt, options, model)
                self.last_model = model
                break
            except _TransientExhausted as exc:
                if index + 1 < len(models):
                    logger.warning(
                        "%s model %s is unavailable (%s); switching to fallback %s", self.provider, model, exc, models[index + 1]
                    )
                    continue
                raise LLMError(f"{self.provider} request failed: {exc}") from exc.__cause__

        tracing.update_span(
            metadata={"provider": str(self.provider), "model": self.last_model, "fallback_used": self.last_model != self.credentials.model}
        )
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMError(f"{self.provider} returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise LLMError(f"{self.provider} returned JSON that is not an object")
        return data
