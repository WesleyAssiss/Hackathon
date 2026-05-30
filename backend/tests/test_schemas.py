from __future__ import annotations

import pytest
from aura.schemas import (
    Citation,
    Claim,
    CounterfactualScenario,
    DecisionDossier,
    PersonaId,
    TurnKind,
)
from pydantic import ValidationError


def _make_citation() -> Citation:
    return Citation(
        knowledge_source_id="ks-1",
        chunk_id="c-1",
        excerpt="evidência sintética",
        relevance=0.8,
    )


def test_propose_claim_rejects_targets() -> None:
    with pytest.raises(ValidationError):
        Claim(
            persona=PersonaId.CFO,
            kind=TurnKind.PROPOSE,
            statement="proposta inicial",
            citations=(_make_citation(),),
            targets=(_make_citation().knowledge_source_id,),  # type: ignore[arg-type]
        )


def test_critique_claim_requires_target() -> None:
    with pytest.raises(ValidationError):
        Claim(
            persona=PersonaId.RED_TEAM,
            kind=TurnKind.CRITIQUE,
            statement="ataque sem alvo",
            citations=(_make_citation(),),
        )


def test_dossier_validates_confidence_interval() -> None:
    with pytest.raises(ValidationError):
        DecisionDossier(
            question="q",
            recommendation="r",
            confidence=0.5,
            confidence_interval=(0.8, 0.2),
            surviving_risks=(),
            counterfactuals=(),
            rounds=(),
        )


def test_counterfactual_probability_bounds() -> None:
    with pytest.raises(ValidationError):
        CounterfactualScenario(
            description="x",
            required_conditions=("y",),
            probability=1.5,
        )
