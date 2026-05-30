from __future__ import annotations

import pytest
from aura.agents import Orchestrator
from aura.schemas import DecisionDossier, StreamEvent, StreamEventKind


@pytest.mark.asyncio
async def test_full_debate_produces_dossier(orchestrator: Orchestrator) -> None:
    events: list[StreamEvent] = []
    dossier: DecisionDossier | None = None
    async for item in orchestrator.run(
        question="Devemos adquirir a startup ACME por $50M?",
        context="Contexto sintético para o teste.",
    ):
        if isinstance(item, StreamEvent):
            events.append(item)
        else:
            dossier = item

    assert dossier is not None
    assert dossier.question.startswith("Devemos adquirir")
    assert 0.0 <= dossier.confidence <= 1.0
    lo, hi = dossier.confidence_interval
    assert lo <= dossier.confidence <= hi

    kinds = {e.kind for e in events}
    assert StreamEventKind.ROUND_STARTED in kinds
    assert StreamEventKind.CLAIM_EMITTED in kinds
    assert StreamEventKind.SCORE_EMITTED in kinds
    assert StreamEventKind.DOSSIER_READY in kinds

    # Sequence numbers are strictly monotonic.
    sequences = [e.sequence for e in events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)


@pytest.mark.asyncio
async def test_duplicate_personas_rejected(orchestrator: Orchestrator) -> None:
    from aura.agents import CFOAgent, Referee
    from aura.knowledge import InMemoryKnowledgeClient, default_demo_corpus
    from aura.llm import MockLLMClient

    llm = MockLLMClient()
    kb = InMemoryKnowledgeClient(default_demo_corpus())
    with pytest.raises(ValueError, match="Duplicate persona_id"):
        Orchestrator(
            agents=[CFOAgent(llm=llm, knowledge=kb), CFOAgent(llm=llm, knowledge=kb)],
            referee=Referee(),
        )
