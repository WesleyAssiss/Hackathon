"""Factory: pick the right LLM/Knowledge stack based on mode + env.

Modos suportados:
    * ``mock``  — 100% offline, sem rede, sem chave. Para CI e ensaios.
    * ``free``  — GitHub Models (PAT do GitHub, gratuito). Para demo real sem Azure.
    * ``azure`` — Azure OpenAI + Azure AI Search (consome crédito Azure).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from aura.config import load_azure_settings
from aura.knowledge import (
    BaseKnowledgeClient,
    InMemoryKnowledgeClient,
    default_demo_corpus,
)
from aura.llm import BaseLLMClient, MockLLMClient

Mode = Literal["mock", "free", "azure"]


def _local_corpus() -> InMemoryKnowledgeClient:
    """Load `data/synthetic/` JSONL if present, else hard-coded demo corpus."""
    override = os.environ.get("AURA_CORPUS_DIR")
    candidates = [Path(override)] if override else [
        Path("data/synthetic"),
        Path(__file__).resolve().parents[2] / "data" / "synthetic",
    ]
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.jsonl")):
            return InMemoryKnowledgeClient.from_jsonl_dir(candidate)
    return InMemoryKnowledgeClient(default_demo_corpus())


def build_llm(mode: Mode, *, gh_model: str | None = None) -> BaseLLMClient:
    if mode == "azure":
        from aura.llm.azure_openai import AzureOpenAIClient

        return AzureOpenAIClient(load_azure_settings())
    if mode == "free":
        from aura.llm.github_models import GitHubModelsClient

        return GitHubModelsClient(model=gh_model)
    return MockLLMClient()


def build_knowledge(mode: Mode) -> BaseKnowledgeClient:
    if mode == "azure":
        from aura.knowledge.foundry_iq_azure import FoundryIQClient

        try:
            return FoundryIQClient(load_azure_settings())
        except RuntimeError:
            return _local_corpus()
    if mode == "free":
        from aura.knowledge.github_models_knowledge import (
            GitHubModelsKnowledgeClient,
        )

        return GitHubModelsKnowledgeClient(_local_corpus())
    return _local_corpus()
