"""Canonical schemas for the AURA debate protocol.

Every artifact crossing a module boundary is one of these models.
Keeping the contract narrow is the single most important architectural
discipline of this codebase — do not add fields opportunistically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PersonaId(StrEnum):
    CFO = "cfo"
    CTO = "cto"
    CUSTOMER = "customer"
    RED_TEAM = "red_team"
    HISTORIAN = "historian"


class TurnKind(StrEnum):
    """The PCDR-Loop turn kinds."""

    PROPOSE = "propose"
    CRITIQUE = "critique"
    DEFEND = "defend"
    CONCEDE = "concede"


class Citation(BaseModel):
    """A grounding citation produced by a Knowledge Source.

    `knowledge_source_id` identifies the upstream KS (e.g. a Foundry IQ
    Knowledge Source). `chunk_id` is opaque to AURA and must round-trip
    so the UI can deep-link back to the original document.
    """

    model_config = ConfigDict(frozen=True)

    knowledge_source_id: str
    chunk_id: str
    excerpt: str = Field(min_length=1, max_length=2000)
    relevance: float = Field(ge=0.0, le=1.0)


class Claim(BaseModel):
    """A single falsifiable claim made by an agent.

    A Claim with zero citations is rejected by the Referee unless
    `kind == "concede"`.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    persona: PersonaId
    kind: TurnKind
    statement: str = Field(min_length=1, max_length=2000)
    citations: tuple[Citation, ...] = ()
    targets: tuple[UUID, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    created_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _validate_targets(self) -> Claim:
        if self.kind in (TurnKind.CRITIQUE, TurnKind.DEFEND) and not self.targets:
            raise ValueError(f"{self.kind} claims must reference at least one target claim")
        if self.kind == TurnKind.PROPOSE and self.targets:
            raise ValueError("propose claims must not target other claims")
        return self


class RefereeScore(BaseModel):
    """Referee evaluation of a single claim."""

    model_config = ConfigDict(frozen=True)

    claim_id: UUID
    groundedness: float = Field(ge=0.0, le=1.0)
    falsifiability: float = Field(ge=0.0, le=1.0)
    survived: bool
    rationale: str = Field(min_length=1, max_length=1000)


class DebateRound(BaseModel):
    """One PCDR round: ordered list of claims plus referee scores."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    claims: tuple[Claim, ...]
    scores: tuple[RefereeScore, ...]


class CounterfactualScenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    description: str = Field(min_length=1, max_length=1000)
    required_conditions: tuple[str, ...]
    probability: float = Field(ge=0.0, le=1.0)


class DecisionDossier(BaseModel):
    """Final output of a debate session — the artifact handed to the user."""

    model_config = ConfigDict(frozen=True)

    debate_id: UUID = Field(default_factory=uuid4)
    question: str
    recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_interval: tuple[float, float]
    surviving_risks: tuple[str, ...]
    counterfactuals: tuple[CounterfactualScenario, ...]
    rounds: tuple[DebateRound, ...]
    created_at: datetime = Field(default_factory=_utcnow)
    # Telemetria de execução: número de chamadas LLM/embed efetivamente
    # realizadas + duração total. Exibido no UI para transparência.
    telemetry: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_ci(self) -> DecisionDossier:
        lo, hi = self.confidence_interval
        if not 0.0 <= lo <= hi <= 1.0:
            raise ValueError("confidence_interval must satisfy 0 <= lo <= hi <= 1")
        return self


# ---------------------------------------------------------------------------
# Streaming events (for SSE)
# ---------------------------------------------------------------------------


class StreamEventKind(StrEnum):
    ROUND_STARTED = "round.started"
    CLAIM_EMITTED = "claim.emitted"
    SCORE_EMITTED = "score.emitted"
    ROUND_FINISHED = "round.finished"
    DOSSIER_READY = "dossier.ready"
    ERROR = "error"


class StreamEvent(BaseModel):
    """Envelope for any SSE event the API streams to the UI."""

    model_config = ConfigDict(frozen=True)

    kind: StreamEventKind
    payload: dict[str, object]
    ts: datetime = Field(default_factory=_utcnow)
    sequence: int = Field(ge=0)


# ---------------------------------------------------------------------------
# API request models
# ---------------------------------------------------------------------------


class DebateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=10, max_length=2000)
    context: str | None = Field(default=None, max_length=8000)
    max_rounds: int = Field(default=3, ge=1, le=5)
    mode: Literal["mock", "free", "azure"] = "mock"
    gh_model: str | None = Field(default=None, max_length=80)
