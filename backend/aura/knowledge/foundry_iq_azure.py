"""Real Foundry IQ adapter — backed by Azure AI Search.

Why AI Search and not the raw azure-ai-projects Knowledge Sources API?
  * AI Search is the GA storage + hybrid-retrieval layer that Foundry IQ
    Knowledge Sources delegate to under the hood. Targeting it directly
    keeps the dependency surface small and lets us run today, while
    remaining swap-compatible with Foundry IQ when its async API stabilises.
  * Persona-scoped filtering is a native ``$filter`` clause, so the
    adversarial protocol (each agent sees only its own evidence) is
    enforced by the index, not by application code.
  * Failure modes are explicit: if the index is missing we degrade to
    ungrounded claims, which the Referee correctly rejects.
"""

from __future__ import annotations

from aura.config import AzureSettings
from aura.knowledge.foundry_iq import BaseKnowledgeClient
from aura.observability import get_logger
from aura.schemas import Citation

_log = get_logger(__name__)


class FoundryIQClient(BaseKnowledgeClient):
    """Production knowledge client backed by Foundry IQ / Azure AI Search."""

    def __init__(self, settings: AzureSettings) -> None:
        if not settings.foundry_configured:
            raise RuntimeError(
                "AURA_FOUNDRY_PROJECT_ENDPOINT is not set; cannot construct FoundryIQClient."
            )
        self._settings = settings
        # Deferred imports — kept lazy so the rest of the app stays
        # importable without the Azure extras installed.
        from azure.identity.aio import (  # type: ignore[import-not-found]
            AzureCliCredential,
            ChainedTokenCredential,
            DefaultAzureCredential,
        )

        self._credential = (
            ChainedTokenCredential(DefaultAzureCredential(), AzureCliCredential())
            if settings.use_managed_identity
            else AzureCliCredential()
        )
        self._search_client = None  # constructed on first call

    async def query(
        self, *, persona_id: str, query: str, top_k: int = 3
    ) -> list[Citation]:
        client = self._ensure_client()
        try:
            response = await client.search(
                search_text=query,
                top=top_k,
                filter=f"persona eq '{persona_id}'",
                query_type="simple",
                select=["chunk_id", "knowledge_source_id", "text"],
            )
            citations: list[Citation] = []
            async for hit in response:
                score = float(hit.get("@search.score", 0.0))
                citations.append(
                    Citation(
                        knowledge_source_id=hit.get("knowledge_source_id", "foundry_iq"),
                        chunk_id=hit.get("chunk_id", hit.get("id", "unknown")),
                        excerpt=str(hit.get("text", ""))[:2000],
                        relevance=min(score / 10.0, 1.0),
                    )
                )
            return citations
        except Exception as exc:  # pragma: no cover — network surface
            _log.warning(
                "aura.foundry.query_failed",
                persona=persona_id,
                error=str(exc),
                exc_type=type(exc).__name__,
            )
            return []

    def _ensure_client(self) -> object:
        if self._search_client is None:
            from azure.search.documents.aio import (  # type: ignore[import-not-found]
                SearchClient,
            )

            self._search_client = SearchClient(
                endpoint=self._settings.foundry_project_endpoint,  # type: ignore[arg-type]
                index_name=self._settings.foundry_knowledge_index,
                credential=self._credential,
            )
        return self._search_client

    async def aclose(self) -> None:
        """Release async clients — call from FastAPI lifespan shutdown."""
        if self._search_client is not None:
            await self._search_client.close()  # type: ignore[attr-defined]
        await self._credential.close()  # type: ignore[attr-defined]
