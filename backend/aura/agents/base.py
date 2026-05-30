"""Council Agent base class and five persona implementations.

Each persona is a thin specialization of `CouncilAgent` that supplies:
  * its `persona_id`
  * a system prompt describing its incentive structure and biases
  * a heuristic for choosing which opposing claim to attack

The PCDR-Loop calls `propose`, `critique` and `defend` in order each round.
Agents are intentionally stateless beyond their `__init__` config — round
state is owned by the Orchestrator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from aura.agents.referee import audit_arithmetic, calibrated_confidence
from aura.knowledge import KnowledgeClient
from aura.llm import LLMClient
from aura.safety import detect, redact
from aura.schemas import Citation, Claim, PersonaId, TurnKind

# Sentinel returned by the LLM when a critic agrees fully with its target.
# Triggers a TurnKind.CONCEDE claim instead of a forced contradiction.
_CONCEDE_SENTINEL = "CONCEDO"


class CouncilAgent(ABC):
    """Base for all council personas."""

    persona_id: PersonaId
    system_prompt: str
    stance: str = ""  # Optional persona-specific stance directive injected into user prompt.

    def __init__(self, *, llm: LLMClient, knowledge: KnowledgeClient) -> None:
        self._llm = llm
        self._knowledge = knowledge

    # ------------------------------------------------------------------
    # Public PCDR API
    # ------------------------------------------------------------------
    async def propose(self, question: str, context: str | None) -> Claim:
        citations = await self._ground(question)
        statement = await self._generate(
            user=_compose_user_prompt(
                "PROPOSE", question, context, citations, stance=self.stance,
            )
        )
        return Claim(
            persona=self.persona_id,
            kind=TurnKind.PROPOSE,
            statement=statement,
            citations=tuple(citations),
            confidence=self._confidence_for(statement, citations, fallback=0.3),
        )

    async def critique(
        self, question: str, opposing_claims: Sequence[Claim]
    ) -> Claim | None:
        target = self._pick_target(opposing_claims)
        if target is None:
            return None
        # Use the target's own statement as the retrieval query — it carries the
        # actual topic keywords, unlike a meta-prefix like "counter-evidence to".
        citations = await self._ground(target.statement)
        # Red-Team is allowed to critique without citations (meta-critic role).
        if not citations and self.persona_id is not PersonaId.RED_TEAM:
            return None
        statement = await self._generate(
            user=_compose_user_prompt(
                "CRITIQUE",
                question,
                context=(
                    f"Alvo da crítica (afirmação de {target.persona.value}): "
                    f"{target.statement}"
                ),
                citations=citations,
                stance=self.stance,
            )
        )
        # Honest-agreement path: if the agent's authentic position aligns with
        # the target, emit a CONCEDE turn so the dossier reflects consensus
        # instead of a forced rhetorical contradiction.
        if _is_concession(statement):
            return Claim(
                persona=self.persona_id,
                kind=TurnKind.CONCEDE,
                statement=f"Concedo o ponto: {target.statement[:200]}",
                targets=(target.id,),
                confidence=0.4,
            )
        return Claim(
            persona=self.persona_id,
            kind=TurnKind.CRITIQUE,
            statement=statement,
            citations=tuple(citations),
            targets=(target.id,),
            confidence=self._confidence_for(
                statement, citations, fallback=0.45,
            ),
        )

    async def defend(
        self,
        question: str,
        critiques_against_me: Sequence[Claim],
        my_prior_claims: Sequence[Claim] = (),
    ) -> Claim | None:
        if not critiques_against_me:
            return None
        attack = critiques_against_me[0]
        # Resolve the original claim under attack so the defense reaffirms it
        # instead of inventing a new (potentially contradictory) position.
        original: Claim | None = None
        if attack.targets and my_prior_claims:
            by_id = {c.id: c for c in my_prior_claims}
            for tid in attack.targets:
                if tid in by_id:
                    original = by_id[tid]
                    break
        # Query on the attack's substantive content, not a meta-prefix.
        citations = await self._ground(attack.statement)
        if not citations:
            # No supporting evidence → concede honestly.
            return Claim(
                persona=self.persona_id,
                kind=TurnKind.CONCEDE,
                statement=f"Concedo o ponto sobre: {attack.statement[:200]}",
                targets=(attack.id,),
                confidence=0.3,
            )
        ctx_lines = [f"Crítica a refutar (de {attack.persona.value}): {attack.statement}"]
        if original is not None:
            ctx_lines.insert(
                0,
                "Sua posição original (que VOCÊ deve reafirmar, não contradizer): "
                f"{original.statement}",
            )
        statement = await self._generate(
            user=_compose_user_prompt(
                "DEFEND",
                question,
                context="\n".join(ctx_lines),
                citations=citations,
                stance=self.stance,
            )
        )
        return Claim(
            persona=self.persona_id,
            kind=TurnKind.DEFEND,
            statement=statement,
            citations=tuple(citations),
            targets=(attack.id,),
            confidence=self._confidence_for(statement, citations, fallback=0.3),
        )

    # ------------------------------------------------------------------
    # Hooks / helpers
    # ------------------------------------------------------------------
    async def _ground(self, query: str) -> list[Citation]:
        raw = await self._knowledge.query(persona_id=self.persona_id.value, query=query)
        # Indirect-injection defense: drop any citation whose excerpt looks
        # like an embedded prompt attack. We log via the rejected count by
        # returning a filtered list — the Referee will then mark thin claims
        # as ungrounded, which is the correct safe outcome.
        return [c for c in raw if not detect(c.excerpt).blocked]

    async def _generate(self, *, user: str) -> str:
        safe_user = redact(user)
        response = await self._llm.complete(system=self.system_prompt, user=safe_user)
        return redact(response.text)

    @abstractmethod
    def _pick_target(self, opposing_claims: Sequence[Claim]) -> Claim | None:
        """Persona-specific heuristic for choosing whom to attack."""

    @staticmethod
    def _initial_confidence(citations: Sequence[Citation]) -> float:
        # Retained for backwards compatibility; the calibrated formula now
        # lives in aura.agents.referee.calibrated_confidence and is used by
        # _confidence_for so that low-relevance fallback citations cannot
        # inflate trust.
        return calibrated_confidence(citations, fallback=0.3)

    @classmethod
    def _confidence_for(
        cls,
        statement: str,
        citations: Sequence[Citation],
        *,
        fallback: float,
    ) -> float:
        # Placeholder responses (LLM failure / content filter) must be
        # untrustworthy so the Referee can reject them.
        if statement.startswith("[Sem resposta") or statement.startswith(
            "[Resposta vazia"
        ):
            return 0.1
        confidence = calibrated_confidence(citations, fallback=fallback)
        # Arithmetic auditor: a claim that contains an obviously wrong
        # computation is internally inconsistent and must be discounted —
        # both to prevent it surviving and to expose it to the Referee.
        if audit_arithmetic(statement):
            confidence = max(confidence - 0.3, 0.1)
        return confidence


def _compose_user_prompt(
    turn: str,
    question: str,
    context: str | None,
    citations: Sequence[Citation],
    *,
    stance: str = "",
) -> str:
    turn_label = {
        "PROPOSE": "Proposta inicial",
        "CRITIQUE": "Crítica construtiva",
        "DEFEND": "Defesa fundamentada",
    }.get(turn, turn.title())
    parts = [f"Etapa atual: {turn_label}.", f"Pergunta de decisão: {question}"]
    if stance:
        parts.append(f"Diretriz da sua persona: {stance}")
    if context:
        parts.append(f"Contexto adicional: {context}")
    if citations:
        parts.append("Evidências disponíveis:")
        for i, c in enumerate(citations, 1):
            parts.append(f"  {i}. ({c.knowledge_source_id} / {c.chunk_id}) {c.excerpt}")
    if turn == "CRITIQUE":
        parts.append(
            "Avalie honestamente o argumento alvo, mantendo SEMPRE o formato "
            "característico da sua persona (descrito acima na diretriz). "
            "Escolha exatamente UM dos três caminhos:\n"
            "  (a) Se discorda genuinamente, comece com 'Discordo porque' e "
            "questione uma premissa específica com nova evidência.\n"
            "  (b) Se concorda parcialmente, comece com 'Concordo, mas...' e "
            "adicione uma ressalva mensurável.\n"
            "  (c) Se concorda integralmente sem ressalva, responda EXATAMENTE "
            "a palavra CONCEDO (em maiúsculas, sem qualquer texto adicional)."
        )
    elif turn == "DEFEND":
        parts.append(
            "Mantenha o formato característico da sua persona (diretriz acima) "
            "e comece com 'Mantenho a posição porque', REAFIRMANDO sua "
            "posição original (mostrada no contexto) e endereçando "
            "diretamente a crítica recebida com nova evidência. "
            "É PROIBIDO inverter ou abandonar sua posição original — "
            "se realmente concorda com a crítica, responda apenas 'CONCEDO'."
        )
    parts.append(
        "Responda em UMA única frase, mensurável e falsificável, com pelo menos "
        "um número concreto e referência a uma das evidências pelo número "
        "(exceto se optou por 'CONCEDO' no caso de crítica)."
    )
    return "\n".join(parts)


def _is_concession(statement: str) -> bool:
    """True when the LLM emitted the explicit CONCEDE sentinel.

    Tolerant of trailing whitespace/punctuation and case variants so that
    a slightly off-format reply ("concedo.") still triggers the concession
    path instead of being treated as a malformed critique.
    """
    head = statement.strip().rstrip(".!?").upper()
    return head == _CONCEDE_SENTINEL or head.startswith(_CONCEDE_SENTINEL + " ")
