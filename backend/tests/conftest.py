"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `scripts/` importable in tests without packaging it.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aura.agents import Orchestrator, Referee, default_council  # noqa: E402
from aura.knowledge import InMemoryKnowledgeClient, default_demo_corpus  # noqa: E402
from aura.llm import MockLLMClient  # noqa: E402


@pytest.fixture
def llm() -> MockLLMClient:
    return MockLLMClient()


@pytest.fixture
def knowledge() -> InMemoryKnowledgeClient:
    return InMemoryKnowledgeClient(default_demo_corpus())


@pytest.fixture
def orchestrator(llm: MockLLMClient, knowledge: InMemoryKnowledgeClient) -> Orchestrator:
    agents = default_council(llm=llm, knowledge=knowledge)
    return Orchestrator(agents=agents, referee=Referee(), max_rounds=2)
