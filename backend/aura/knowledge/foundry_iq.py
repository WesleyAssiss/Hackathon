"""Knowledge Source client — abstract + mock impl backed by in-memory corpus.

The real Foundry IQ adapter (D2) wraps Azure AI Search (the storage layer
Foundry IQ Knowledge Sources delegate to under the hood) and exposes the
same `query` contract.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aura.schemas import Citation


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    knowledge_source_id: str
    chunk_id: str
    text: str
    keywords: frozenset[str]


class KnowledgeClient(Protocol):
    async def query(self, *, persona_id: str, query: str, top_k: int = 3) -> list[Citation]: ...


class BaseKnowledgeClient(ABC):
    @abstractmethod
    async def query(
        self, *, persona_id: str, query: str, top_k: int = 3
    ) -> list[Citation]: ...


class InMemoryKnowledgeClient(BaseKnowledgeClient):
    """Mock Foundry IQ backed by an in-memory corpus per persona.

    Scoring is a naive keyword-overlap heuristic — enough for deterministic
    tests and the local demo. The real adapter delegates ranking to Foundry
    IQ / Azure AI Search hybrid retrieval.
    """

    def __init__(self, corpus: dict[str, Sequence[KnowledgeChunk]]) -> None:
        self._corpus = {persona: tuple(chunks) for persona, chunks in corpus.items()}

    @classmethod
    def from_jsonl_dir(cls, directory: str | Path) -> InMemoryKnowledgeClient:
        """Load a corpus emitted by ``scripts/gen_synthetic_data.py``.

        Each ``{persona}.jsonl`` file holds one record per line. Falls back
        to ``default_demo_corpus()`` if the directory is empty/missing.
        """
        root = Path(directory)
        corpus: dict[str, list[KnowledgeChunk]] = {}
        if not root.is_dir():
            return cls(default_demo_corpus())
        for jsonl in sorted(root.glob("*.jsonl")):
            persona = jsonl.stem
            chunks: list[KnowledgeChunk] = []
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                chunks.append(
                    KnowledgeChunk(
                        knowledge_source_id=record.get(
                            "knowledge_source_id", f"synthetic_{persona}"
                        ),
                        chunk_id=record["chunk_id"],
                        text=record["text"],
                        keywords=frozenset(_tokenize(record["text"])),
                    )
                )
            if chunks:
                corpus[persona] = chunks
        return cls(corpus or default_demo_corpus())

    async def query(
        self, *, persona_id: str, query: str, top_k: int = 3
    ) -> list[Citation]:
        chunks = self._corpus.get(persona_id, ())
        if not chunks:
            return []
        query_tokens = frozenset(_tokenize(query))
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in chunks:
            overlap = len(query_tokens & chunk.keywords)
            if overlap == 0:
                continue
            relevance = overlap / max(len(query_tokens), 1)
            scored.append((relevance, chunk))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        # Fallback: if keyword overlap yields nothing, surface the persona's
        # top chunks at low relevance so the debate is always grounded in
        # *some* prior knowledge instead of going silent. The referee will
        # still penalize weak grounding, so this does not bias the verdict.
        if not scored:
            scored = [(0.15, chunk) for chunk in chunks[:top_k]]
        return [
            Citation(
                knowledge_source_id=chunk.knowledge_source_id,
                chunk_id=chunk.chunk_id,
                excerpt=chunk.text[:2000],
                relevance=min(relevance, 1.0),
            )
            for relevance, chunk in scored[:top_k]
        ]


def _tokenize(text: str) -> list[str]:
    return [t.lower().strip(".,;:!?\"'()[]") for t in text.split() if len(t) > 2]


def iter_corpus_records(
    corpus: dict[str, Iterable[KnowledgeChunk]],
) -> Iterable[dict[str, str]]:
    """Yield AI-Search-ready documents from any in-memory corpus."""
    for persona, chunks in corpus.items():
        for chunk in chunks:
            yield {
                "id": f"{persona}-{chunk.chunk_id}",
                "persona": persona,
                "chunk_id": chunk.chunk_id,
                "knowledge_source_id": chunk.knowledge_source_id,
                "text": chunk.text,
            }


def default_demo_corpus() -> dict[str, list[KnowledgeChunk]]:
    """Synthetic demo corpus — keep additions strictly synthetic/public."""
    return {
        "cfo": [
            KnowledgeChunk(
                knowledge_source_id="synthetic_market_reports",
                chunk_id="acme-burn-2026q1",
                text=(
                    "ACME Q1 2026 synthetic financials show a monthly burn of $2.1M with "
                    "12 months of runway and declining gross margin (from 41% to 34%)."
                ),
                keywords=frozenset({"acme", "burn", "runway", "financials", "margin", "acquire"}),
            ),
        ],
        "cto": [
            KnowledgeChunk(
                knowledge_source_id="synthetic_company_tech_stacks",
                chunk_id="acme-stack",
                text=(
                    "ACME runs a Rust + Postgres + Kafka stack with proprietary inference "
                    "kernels that would accelerate the roadmap by an estimated 18 months."
                ),
                keywords=frozenset({"acme", "stack", "rust", "kafka", "inference", "acquire"}),
            ),
        ],
        "customer": [
            KnowledgeChunk(
                knowledge_source_id="synthetic_g2_reviews",
                chunk_id="acme-nps",
                text=(
                    "Synthetic ACME review corpus reports NPS -10 with 40% annual churn "
                    "driven by onboarding friction and unreliable SLAs."
                ),
                keywords=frozenset({"acme", "nps", "churn", "customer", "reviews"}),
            ),
        ],
        "red_team": [
            KnowledgeChunk(
                knowledge_source_id="nvd_cve_subset",
                chunk_id="cve-2025-9999",
                text=(
                    "CVE-2025-9999 affects a Rust crate used in ACME's pipeline; CVSS 9.1. "
                    "Patched upstream in v2.1, but production ACME deployments lag 4 versions."
                ),
                keywords=frozenset({"acme", "cve", "vulnerability", "patch", "rust"}),
            ),
        ],
        "historian": [
            KnowledgeChunk(
                knowledge_source_id="hbr_failure_patterns",
                chunk_id="acquisition-failure-2024",
                text=(
                    "Public failure-pattern study: 73% of sub-$100M acquisitions fail to "
                    "integrate within 24 months, primarily due to cultural mismatch."
                ),
                keywords=frozenset({"acquisition", "failure", "integration", "cultural", "acme"}),
            ),
        ],
    }
