"""Orchestrator: drives the PCDR-Loop across the Council and the Referee.

Single entry-point: `Orchestrator.run(...)` is an async generator that yields
`StreamEvent`s in real time AND ultimately the final `DecisionDossier`.
This dual-purpose generator is what the FastAPI SSE route consumes.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncIterator, Sequence
from itertools import count
from typing import Any

from aura.agents.base import CouncilAgent
from aura.agents.referee import Referee
from aura.schemas import (
    Claim,
    DebateRound,
    DecisionDossier,
    PersonaId,
    RefereeScore,
    StreamEvent,
    StreamEventKind,
)


class Orchestrator:
    def __init__(
        self,
        *,
        agents: Sequence[CouncilAgent],
        referee: Referee,
        max_rounds: int = 3,
        convergence_entropy: float = 0.35,
        skip_defend_below: float = 0.4,
    ) -> None:
        if len({a.persona_id for a in agents}) != len(agents):
            raise ValueError("Duplicate persona_id in agent roster")
        self._agents = tuple(agents)
        self._referee = referee
        self._max_rounds = max_rounds
        self._converge_at = convergence_entropy
        # If a critique scores below this groundedness threshold, the defend
        # phase is skipped for that attack — defending a weak critique wastes
        # LLM calls and dilutes the dossier.
        self._skip_defend_below = skip_defend_below

    async def run(
        self, *, question: str, context: str | None
    ) -> AsyncIterator[StreamEvent | DecisionDossier]:
        seq = count()
        rounds: list[DebateRound] = []
        prior_claims_by_persona: dict[PersonaId, list[Claim]] = {
            a.persona_id: [] for a in self._agents
        }
        started_at = time.perf_counter()

        for round_idx in range(self._max_rounds):
            yield _ev(seq, StreamEventKind.ROUND_STARTED, {"round": round_idx})

            round_claims: list[Claim] = []
            critique_scores: dict[Any, RefereeScore] = {}

            # PROPOSE (round 0) OR CRITIQUE+DEFEND (subsequent rounds).
            # Personas within a phase are INDEPENDENT, so we fan them out via
            # asyncio.gather. This cuts wall-clock latency by N (number of
            # personas) per phase, the single biggest UX win we have.
            if round_idx == 0:
                proposals = await asyncio.gather(
                    *(agent.propose(question, context) for agent in self._agents),
                    return_exceptions=False,
                )
                for agent, claim in zip(self._agents, proposals, strict=True):
                    round_claims.append(claim)
                    prior_claims_by_persona[agent.persona_id].append(claim)
                    yield _ev(seq, StreamEventKind.CLAIM_EMITTED, _claim_payload(claim))
            else:
                # All claims from the previous round are fair game for critique.
                previous = rounds[-1].claims
                opposing_per_agent = [
                    [c for c in previous if c.persona is not agent.persona_id]
                    for agent in self._agents
                ]
                critiques = await asyncio.gather(
                    *(
                        agent.critique(question, opposing)
                        for agent, opposing in zip(
                            self._agents, opposing_per_agent, strict=True
                        )
                    ),
                    return_exceptions=False,
                )
                # Score critiques eagerly so we can skip weak defends.
                for agent, critique in zip(self._agents, critiques, strict=True):
                    if critique is None:
                        continue
                    round_claims.append(critique)
                    prior_claims_by_persona[agent.persona_id].append(critique)
                    yield _ev(
                        seq, StreamEventKind.CLAIM_EMITTED, _claim_payload(critique)
                    )
                    critique_scores[critique.id] = self._referee.score(critique)

                # DEFEND: every agent gets to rebut critiques aimed at any of
                # its claims — but ONLY if the critique scored above the skip
                # threshold. Defending against trivial / ungrounded attacks
                # wastes LLM calls.
                my_claim_ids: dict[PersonaId, set] = {
                    a.persona_id: {c.id for c in prior_claims_by_persona[a.persona_id]}
                    for a in self._agents
                }
                defend_inputs: list[tuple[CouncilAgent, list[Claim]]] = []
                for agent in self._agents:
                    attacks = [
                        c
                        for c in round_claims
                        if c.targets
                        and any(t in my_claim_ids[agent.persona_id] for t in c.targets)
                        and critique_scores.get(c.id) is not None
                        and critique_scores[c.id].groundedness
                        >= self._skip_defend_below
                    ]
                    if attacks:
                        defend_inputs.append((agent, attacks))
                if defend_inputs:
                    defenses = await asyncio.gather(
                        *(
                            agent.defend(
                                question,
                                attacks,
                                my_prior_claims=prior_claims_by_persona[agent.persona_id],
                            )
                            for agent, attacks in defend_inputs
                        ),
                        return_exceptions=False,
                    )
                    for (agent, _), defense in zip(
                        defend_inputs, defenses, strict=True
                    ):
                        if defense is not None:
                            round_claims.append(defense)
                            prior_claims_by_persona[agent.persona_id].append(defense)
                            yield _ev(
                                seq,
                                StreamEventKind.CLAIM_EMITTED,
                                _claim_payload(defense),
                            )

            # Score every claim emitted in this round.
            scores: list[RefereeScore] = []
            for c in round_claims:
                # Reuse already-scored critiques to avoid double-evaluation.
                cached = critique_scores.get(c.id) if round_idx > 0 else None
                score = cached if cached is not None else self._referee.score(c)
                scores.append(score)
                yield _ev(seq, StreamEventKind.SCORE_EMITTED, _score_payload(score))

            rounds.append(
                DebateRound(index=round_idx, claims=tuple(round_claims), scores=tuple(scores))
            )
            yield _ev(seq, StreamEventKind.ROUND_FINISHED, {"round": round_idx})

            survived_count = sum(1 for s in scores if s.survived)
            if (
                _entropy(scores) < self._converge_at
                and round_idx >= 1
                and survived_count > 0
            ):
                break  # Early convergence — no point belaboring an agreed-upon answer.

        dossier = self._referee.aggregate(question=question, rounds=rounds)

        # Attach execution telemetry by rebuilding the (frozen) dossier with
        # the populated telemetry dict. Best-effort: any introspection failure
        # leaves the dossier untouched.
        try:
            elapsed = time.perf_counter() - started_at
            telemetry: dict[str, float] = {"elapsed_s": round(elapsed, 2)}
            # Walk through agents to read LLM + knowledge client stats.
            seen_llm: set[int] = set()
            seen_kb: set[int] = set()
            llm_calls = 0
            llm_errors = 0
            emb_hits = 0
            emb_misses = 0
            for agent in self._agents:
                llm = getattr(agent, "_llm", None)
                if llm is not None and id(llm) not in seen_llm:
                    seen_llm.add(id(llm))
                    stats = getattr(llm, "call_stats", None)
                    if stats:
                        llm_calls += stats.get("calls", 0)
                        llm_errors += stats.get("errors", 0)
                kb = getattr(agent, "_knowledge", None)
                if kb is not None and id(kb) not in seen_kb:
                    seen_kb.add(id(kb))
                    cstats = getattr(kb, "cache_stats", None)
                    if cstats:
                        emb_hits += cstats.get("hits", 0)
                        emb_misses += cstats.get("misses", 0)
            telemetry["llm_calls"] = llm_calls
            telemetry["llm_errors"] = llm_errors
            telemetry["embed_calls"] = emb_misses  # only misses hit the network
            telemetry["embed_cache_hits"] = emb_hits
            total_personas = len(self._agents)
            telemetry["personas"] = total_personas
            telemetry["rounds_run"] = len(rounds)
            dossier = dossier.model_copy(update={"telemetry": telemetry})
        except Exception:
            pass

        yield _ev(
            seq, StreamEventKind.DOSSIER_READY, {"dossier_id": str(dossier.debate_id)}
        )
        yield dossier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ev(seq: count, kind: StreamEventKind, payload: dict[str, Any]) -> StreamEvent:
    return StreamEvent(kind=kind, payload=payload, sequence=next(seq))


def _claim_payload(claim: Claim) -> dict[str, Any]:
    return {
        "claim_id": str(claim.id),
        "persona": claim.persona.value,
        "kind": claim.kind.value,
        "statement": claim.statement,
        "confidence": claim.confidence,
        "targets": [str(t) for t in claim.targets],
        "citations": [
            {
                "knowledge_source_id": c.knowledge_source_id,
                "chunk_id": c.chunk_id,
                "relevance": c.relevance,
            }
            for c in claim.citations
        ],
    }


def _score_payload(score: RefereeScore) -> dict[str, Any]:
    return {
        "claim_id": str(score.claim_id),
        "groundedness": score.groundedness,
        "falsifiability": score.falsifiability,
        "survived": score.survived,
        "rationale": score.rationale,
    }


def _entropy(scores: Sequence[RefereeScore]) -> float:
    """Shannon entropy of survived/not-survived distribution.

    Used as a convergence heuristic: when nearly all claims agree on
    surviving (or not), there is little value in additional rounds.
    """
    if not scores:
        return 1.0
    survived = sum(1 for s in scores if s.survived)
    total = len(scores)
    p = survived / total
    if p in (0.0, 1.0):
        return 0.0
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
