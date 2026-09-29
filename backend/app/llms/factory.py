"""Choose credentials and build the right client.

Resolution order: the user's own key (their preferred provider first), then the server-wide key
(LLM_DEFAULT_PROVIDER first). No key at all means callers use deterministic logic instead.
"""

import logging
from typing import Dict, Optional, Tuple

from app.config import settings
from app.enums import LLMProvider
from app.llms.base import GenerationOptions, LLMClient, LLMCredentials, LLMError
from app.llms.gemini_client import GeminiClient
from app.llms.openai_client import OpenAIClient
from app.models.user import User
from app.utils.security import decrypt_secret

logger = logging.getLogger(__name__)

_CLIENTS = {LLMProvider.GEMINI: GeminiClient, LLMProvider.OPENAI: OpenAIClient}


def model_for(provider: LLMProvider) -> str:
    return settings.GEMINI_MODEL if provider == LLMProvider.GEMINI else settings.OPENAI_MODEL


def fallback_model_for(provider: LLMProvider) -> Optional[str]:
    return settings.GEMINI_FALLBACK_MODEL if provider == LLMProvider.GEMINI else settings.OPENAI_FALLBACK_MODEL


def _order(preferred: Optional[str]) -> list[LLMProvider]:
    first = LLMProvider(preferred) if preferred in (LLMProvider.GEMINI, LLMProvider.OPENAI) else LLMProvider(settings.LLM_DEFAULT_PROVIDER)
    return [first] + [p for p in LLMProvider if p != first]


def resolve_credentials(user: Optional[User]) -> Optional[LLMCredentials]:
    user_keys: Dict[LLMProvider, Optional[str]] = {}
    if user is not None:
        user_keys = {
            LLMProvider.GEMINI: decrypt_secret(user.gemini_api_key_encrypted),
            LLMProvider.OPENAI: decrypt_secret(user.openai_api_key_encrypted),
        }
    server_keys = {LLMProvider.GEMINI: settings.GEMINI_API_KEY, LLMProvider.OPENAI: settings.OPENAI_API_KEY}
    order = _order(user.preferred_llm_provider if user else None)

    for keys in (user_keys, server_keys):
        for provider in order:
            if keys.get(provider):
                return LLMCredentials(
                    provider=provider, api_key=keys[provider], model=model_for(provider), fallback_model=fallback_model_for(provider)
                )
    return None


def get_llm_client(credentials: LLMCredentials) -> LLMClient:
    return _CLIENTS[credentials.provider](credentials)


def get_llm_for_user(user: Optional[User]) -> Optional[LLMClient]:
    credentials = resolve_credentials(user)
    return get_llm_client(credentials) if credentials else None


async def test_api_key(provider: LLMProvider, api_key: str, model: Optional[str] = None) -> Tuple[bool, str]:
    client = get_llm_client(LLMCredentials(provider=provider, api_key=api_key, model=model or model_for(provider)))
    try:
        await client.generate_json("Reply with a JSON object.", 'Return {"ok": true}.', GenerationOptions(max_output_tokens=256))
    except LLMError as exc:
        logger.info("API key test failed for %s: %s", provider, exc)
        return False, f"The {provider} key could not be verified ({exc})."
    return True, f"The {provider} key works with model {client.credentials.model}."
