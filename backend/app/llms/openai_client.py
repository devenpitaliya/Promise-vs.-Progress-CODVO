from app.config import settings
from app.llms.base import GenerationOptions, LLMClient
from app.utils import tracing


class OpenAIClient(LLMClient):
    """OpenAI or any OpenAI-compatible endpoint (OPENAI_BASE_URL), e.g. Azure OpenAI or a self-hosted gateway."""

    async def _complete(self, system_prompt: str, user_prompt: str, options: GenerationOptions, model: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.credentials.api_key,
            base_url=settings.OPENAI_BASE_URL,
            timeout=options.timeout_seconds,
        )
        completion = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=options.temperature,
            max_tokens=options.max_output_tokens,
        )
        usage = completion.usage
        if usage is not None:
            tracing.record_usage(
                model,
                usage.prompt_tokens,
                usage.completion_tokens,
                reasoning_tokens=getattr(usage.completion_tokens_details, "reasoning_tokens", None),
                cached_tokens=getattr(usage.prompt_tokens_details, "cached_tokens", None),
            )
        return completion.choices[0].message.content or ""
