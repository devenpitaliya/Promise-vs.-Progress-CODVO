from app.llms.base import GenerationOptions, LLMClient
from app.utils import tracing


class GeminiClient(LLMClient):
    async def _complete(self, system_prompt: str, user_prompt: str, options: GenerationOptions, model: str) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.credentials.api_key)
        response = await client.aio.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=options.temperature,
                max_output_tokens=options.max_output_tokens,
                # We never pass tools; disabling AFC also silences the SDK's AFC warnings.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        usage = response.usage_metadata
        if usage is not None:
            # Thinking tokens are billed as output.
            output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
            tracing.record_usage(
                model,
                usage.prompt_token_count,
                output_tokens,
                thinking_tokens=usage.thoughts_token_count,
                cached_tokens=usage.cached_content_token_count,
            )
        return response.text or ""
