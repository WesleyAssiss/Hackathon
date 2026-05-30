"""Azure OpenAI adapter implementing the `LLMClient` protocol.

Uses Managed Identity by default; falls back to `AzureCliCredential` for local
dev. Azure SDK imports are deferred so the package remains importable in
environments without `azure-*` extras installed (e.g., CI for the mock path).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aura.config import AzureSettings
from aura.llm.client import BaseLLMClient, LLMResponse

if TYPE_CHECKING:
    pass


class AzureOpenAIClient(BaseLLMClient):
    """Thin async wrapper around `openai.AsyncAzureOpenAI` configured with
    Azure AD token authentication via `azure-identity`.
    """

    def __init__(self, settings: AzureSettings) -> None:
        if not settings.aoai_configured:
            raise RuntimeError(
                "AURA_AOAI_ENDPOINT is not set; cannot construct AzureOpenAIClient."
            )
        # Deferred imports → only required when Azure mode is actually used.
        from azure.identity import (  # type: ignore[import-not-found]
            AzureCliCredential,
            ChainedTokenCredential,
            DefaultAzureCredential,
            get_bearer_token_provider,
        )
        from openai import AsyncAzureOpenAI  # type: ignore[import-not-found]

        credential = (
            ChainedTokenCredential(DefaultAzureCredential(), AzureCliCredential())
            if settings.use_managed_identity
            else AzureCliCredential()
        )
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        self._deployment = settings.aoai_deployment
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.aoai_endpoint,  # type: ignore[arg-type]
            azure_ad_token_provider=token_provider,
            api_version=settings.aoai_api_version,
        )

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 512
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
            top_p=0.9,
        )
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        # `logprobs` are not always available — fall back to a calibrated default.
        confidence = 0.7 if choice.finish_reason == "stop" else 0.5
        return LLMResponse(text=text, confidence=confidence)
