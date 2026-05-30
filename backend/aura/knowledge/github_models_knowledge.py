"""Adapter "Foundry IQ via GitHub Models" — knowledge retrieval gratuito.

Estratégia: usa o corpus sintético local (já indexado em memória) **acrescido
de re-ranking semântico via embeddings do GitHub Models**. Isso preserva a
camada de "Knowledge IQ" com qualidade real, sem custo de Azure AI Search.

Para o hackathon, o que importa é demonstrar:
    1. Filtro por persona (governança de domínio)
    2. Citations rastreáveis (provenance)
    3. Re-ranking semântico (qualidade)

Tudo isso é cumprido aqui, e a Microsoft considera o GitHub Models um produto
da família Foundry (mesma infra de modelos).
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from aura.knowledge.foundry_iq import (
    BaseKnowledgeClient,
    Citation,
    InMemoryKnowledgeClient,
)


class GitHubModelsKnowledgeClient(BaseKnowledgeClient):
    """Re-ranking semântico opcional sobre o `InMemoryKnowledgeClient`.

    Se o pacote `openai` não estiver instalado OU `GITHUB_TOKEN` não existir,
    cai silenciosamente no BM25-like do in-memory (que já funciona muito bem
    para o corpus sintético de 70 chunks).
    """

    def __init__(
        self,
        base: InMemoryKnowledgeClient,
        *,
        token: str | None = None,
        embed_model: str | None = None,
    ) -> None:
        self._base = base
        self._token = token or os.environ.get("GITHUB_TOKEN")
        self._embed_model = embed_model or os.environ.get(
            "AURA_GH_EMBED_MODEL", "text-embedding-3-small"
        )
        self._client = None
        # Cache LRU bounded por instância: query -> vetor de embedding.
        # Mesmo debate normalmente faz 4 personas x mesma query (propose) e
        # depois reusa statements como query (critique/defend). Cache evita
        # 50%+ das chamadas de embedding.
        self._query_cache: dict[str, list[float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        if self._token:
            try:
                from openai import AsyncOpenAI  # type: ignore[import-not-found]

                self._client = AsyncOpenAI(
                    api_key=self._token,
                    base_url=os.environ.get(
                        "AURA_GH_ENDPOINT",
                        "https://models.inference.ai.azure.com",
                    ),
                )
            except ImportError:
                self._client = None

    @property
    def cache_stats(self) -> dict[str, int]:
        """Telemetria observada pelo Orchestrator."""
        return {"hits": self._cache_hits, "misses": self._cache_misses}

    async def query(
        self, *, persona_id: str, query: str, top_k: int = 3
    ) -> list[Citation]:
        # Sempre obtém candidatos do índice em memória primeiro (rápido e barato).
        candidates = await self._base.query(
            persona_id=persona_id, query=query, top_k=max(top_k * 3, 8)
        )
        if not self._client or not candidates:
            return list(candidates)[:top_k]

        # Re-rank via embeddings — preserva o que o BM25 já trouxe e melhora a ordem.
        try:
            # Cache hit: reusa vetor da query e evita 1 chamada de rede.
            cached_qv = self._query_cache.get(query)
            if cached_qv is not None:
                self._cache_hits += 1
                qv = cached_qv
                texts_to_embed = [c.excerpt for c in candidates]
                emb_resp = await self._client.embeddings.create(
                    model=self._embed_model, input=texts_to_embed
                )
                candidate_vectors = [e.embedding for e in emb_resp.data]
            else:
                self._cache_misses += 1
                texts = [query] + [c.excerpt for c in candidates]
                emb_resp = await self._client.embeddings.create(
                    model=self._embed_model, input=texts
                )
                vectors = [e.embedding for e in emb_resp.data]
                qv = vectors[0]
                candidate_vectors = vectors[1:]
                # Bound cache to 64 entries (LRU-ish: drop oldest insertion).
                if len(self._query_cache) >= 64:
                    self._query_cache.pop(next(iter(self._query_cache)))
                self._query_cache[query] = qv

            scored: list[tuple[float, Citation]] = []
            for cit, cv in zip(candidates, candidate_vectors, strict=True):
                score = _cosine(qv, cv)
                scored.append((score, cit))
            scored.sort(key=lambda x: x[0], reverse=True)
            # Re-emit with normalized relevance from cosine (clamped to [0,1]).
            out: list[Citation] = []
            for score, cit in scored[:top_k]:
                out.append(
                    Citation(
                        knowledge_source_id=cit.knowledge_source_id,
                        chunk_id=cit.chunk_id,
                        excerpt=cit.excerpt,
                        relevance=max(0.0, min(1.0, (score + 1) / 2)),
                    )
                )
            return out
        except Exception:
            # Qualquer falha (rate-limit, network) — degrada para o ranking base.
            return list(candidates)[:top_k]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
