"""Referee: evaluates claims for groundedness and falsifiability, and
aggregates surviving claims into a calibrated posterior over the decision.

This is intentionally a small, transparent rule-based component — the goal
is auditability, not opacity. The LLM-as-judge variant is wired in D4 as
an optional refinement, but the deterministic core remains the source of
truth so traces are reproducible.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from statistics import mean
from typing import Literal

from aura.schemas import (
    Citation,
    Claim,
    CounterfactualScenario,
    DebateRound,
    DecisionDossier,
    PersonaId,
    RefereeScore,
    TurnKind,
)

_MIN_STATEMENT_TOKENS = 6
_FALSIFIABILITY_MARKERS = (
    " porque ",
    " because ",
    " evidência ",
    " evidence ",
    " dado ",
    " indica ",
    " mostra ",
    " demonstra ",
)

# ---------------------------------------------------------------------------
# Stance classification — content-first, with persona prior as fallback
# ---------------------------------------------------------------------------

Stance = Literal["for", "against", "neutral"]

# Portuguese + English lexical markers. Order matters: phrases checked before
# individual tokens, AGAINST checked before FOR because rejection vocabulary
# is more discriminative (a sentence may contain both "lançar" and "não
# devemos" — the negation must win).
_AGAINST_PHRASES = (
    "não devemos", "nao devemos", "não recomendo", "nao recomendo",
    "não prosseguir", "nao prosseguir", "devemos rejeitar", "devemos adiar",
    "devemos evitar", "devemos pausar", "devemos cancelar", "discordo",
    "rejeitar", "do not", "should not", "must not", "shouldn't",
    "ponto fraco",
    # "yes-but" rhetorical pattern is adversarial in disguise: the speaker
    # nominally agrees but the substantive clause weakens the proposition.
    "concordo, mas", "concordo mas", "concordo, porém", "concordo porem",
    "de acordo, mas", "de acordo mas",
)
# Stem prefixes — match any inflection (rejeito/rejeita/rejeitar/rejeitamos,
# compromete/comprometer/comprometendo, falha/falham/falhou/falhar, …).
_AGAINST_STEMS = (
    "rejeit", "compromet", "falh", "fracass", "inviabiliz", "piora",
    "deteriora", "degrada", "impossibilita", "obstr", "impede",
)
_AGAINST_TOKENS = (
    "risco", "riscos", "fragiliza", "fragilidade", "downside", "perda",
    "queda", "cai", "downtime", "churn", "ameaça", "ameaca",
    "inviável", "inviavel", "vulnerável", "vulneravel",
    "contra-indicado", "contraindicado",
)
_FOR_PHRASES = (
    "devemos lançar", "devemos lancar", "devemos prosseguir",
    "devemos aprovar", "devemos adquirir", "devemos investir",
    "devemos avançar", "devemos avancar", "recomendo prosseguir",
    "recomendo aprovar", "recomendo lançar", "recomendo lancar",
    "deveríamos lançar", "deveriamos lancar",
    "should proceed", "should approve", "should launch",
    "mantenho a posição", "mantenho a posicao",
)
_FOR_TOKENS = (
    "viável", "viavel", "favorável", "favoravel", "vantagem", "oportunidade",
    "retorno", "lucro", "crescimento", "expansão", "expansao", "aprovar",
    "prosseguir",
)

# Persona-level prior used ONLY as fallback when content is genuinely neutral.
# Personas whose role is intrinsically adversarial (CFO/Red-Team push back on
# proposals by mandate) keep a directional prior. Personas who genuinely
# argue both sides depending on the topic (CTO weighs feasibility, Historian
# cites base-rates that can favor or oppose) stay neutral so that the
# observed content drives classification.
_PERSONA_PRIOR: dict[PersonaId, Stance] = {
    PersonaId.CFO: "against",
    PersonaId.CTO: "neutral",
    PersonaId.HISTORIAN: "neutral",
    PersonaId.CUSTOMER: "against",
    PersonaId.RED_TEAM: "against",
}


def _classify_stance(claim: Claim) -> Stance:
    """Return the claim's stance on the underlying proposition.

    Content-based detection (lexical markers in Portuguese/English) takes
    precedence over the persona prior so that, e.g., a CTO who actually
    argues for *not* launching is counted on the AGAINST side.

    Concessions are explicitly neutral (they shrink no posterior mass).
    """
    if claim.kind is TurnKind.CONCEDE:
        return "neutral"
    text = f" {claim.statement.lower()} "
    against_hits = (
        sum(1 for p in _AGAINST_PHRASES if p in text)
        + sum(
            1 for t in _AGAINST_TOKENS
            if f" {t} " in text or f" {t}." in text or f" {t}," in text
        )
        + sum(1 for s in _AGAINST_STEMS if f" {s}" in text)
    )
    for_hits = sum(1 for p in _FOR_PHRASES if p in text) + sum(
        1 for t in _FOR_TOKENS if f" {t} " in text or f" {t}." in text or f" {t}," in text
    )
    if against_hits > for_hits:
        return "against"
    if for_hits > against_hits:
        return "for"
    return _PERSONA_PRIOR.get(claim.persona, "neutral")


# ---------------------------------------------------------------------------
# Arithmetic auditor — flags obvious internal inconsistencies in LLM output
# ---------------------------------------------------------------------------

# Matches "<num>[unit] <op> <num>[unit] = <num>[unit]" OR the reverse
# "<num>[unit] = <num>[unit] <op> <num>[unit]". Operators *, x, xd7, +, -, /.
# Numbers may include thousands/decimals (Portuguese or English notation),
# an optional currency prefix (R$, US$, $, €, £) and an optional unit
# suffix (M, k, mi, mil, bi, %). Tolerant of surrounding text; only
# explicit equations are audited (false positives in a demo are worse
# than missed inferences).
_CUR = r"(?:r\$|us\$|\$|€|£)?\s*"
_NUM_CORE = r"(\d+(?:[.,]\d+)?)\s*(?:m|mi|mil|k|%|bi|b)?"
_NUM = _CUR + _NUM_CORE
_OP = r"([x\xd7*+\-/])"
_ARITH_FORWARD = re.compile(
    rf"{_NUM}\s*{_OP}\s*{_NUM}\s*=\s*{_NUM}", re.IGNORECASE,
)
_ARITH_REVERSE = re.compile(
    rf"{_NUM}\s*=\s*{_NUM}\s*{_OP}\s*{_NUM}", re.IGNORECASE,
)


def _parse_number(raw: str) -> float:
    s = raw.replace(" ", "")
    # Treat ',' as decimal separator if there is exactly one and no '.'
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        # Mixed format → assume '.' thousands, ',' decimals (PT-BR style).
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def audit_arithmetic(statement: str, *, tolerance: float = 0.05) -> list[str]:
    """Return a list of human-readable issues found in arithmetic claims.

    Empty list = no inconsistency detected. Tolerance is relative
    (5% by default) to avoid flagging legitimate rounding ("≈").
    Only explicit equations (containing '=') are audited.
    """
    issues: list[str] = []

    def _check(a_raw: str, op: str, b_raw: str, r_raw: str) -> None:
        try:
            a, b, r = _parse_number(a_raw), _parse_number(b_raw), _parse_number(r_raw)
        except ValueError:
            return
        if op in ("x", "X", "\xd7", "*"):
            expected = a * b
        elif op == "+":
            expected = a + b
        elif op == "-":
            expected = a - b
        elif op == "/":
            if b == 0:
                return
            expected = a / b
        else:
            return
        denom = max(abs(expected), abs(r), 1e-9)
        if abs(expected - r) / denom > tolerance:
            issues.append(
                f"{a_raw} {op} {b_raw} = {r_raw} (esperado ≈ {expected:.4g})"
            )

    for match in _ARITH_FORWARD.finditer(statement):
        a_raw, op, b_raw, r_raw = match.groups()
        _check(a_raw, op, b_raw, r_raw)
    for match in _ARITH_REVERSE.finditer(statement):
        # "R = A op B" → reuse the same forward check.
        r_raw, a_raw, op, b_raw = match.groups()
        _check(a_raw, op, b_raw, r_raw)
    return issues


class Referee:
    """Scores claims and aggregates surviving evidence into a posterior."""

    def __init__(
        self,
        *,
        groundedness_threshold: float = 0.5,
        falsifiability_threshold: float = 0.4,
    ) -> None:
        self._g_threshold = groundedness_threshold
        self._f_threshold = falsifiability_threshold

    # ------------------------------------------------------------------
    # Per-claim scoring
    # ------------------------------------------------------------------
    def score(self, claim: Claim) -> RefereeScore:
        if claim.kind is TurnKind.CONCEDE:
            return RefereeScore(
                claim_id=claim.id,
                groundedness=1.0,
                falsifiability=1.0,
                survived=False,  # a concession does not "survive" as evidence
                rationale="Concessão explícita registrada.",
            )

        # Provider-level fallbacks (rate-limit, content-filter, empty response)
        # are emitted as bracketed sentinels by the LLM adapter. They carry
        # NO informational content and must never survive scoring — otherwise
        # they pollute the dossier as "risks" and skew the posterior.
        stmt = claim.statement.lstrip()
        if stmt.startswith("[Sem resposta") or stmt.startswith("[Resposta vazia"):
            return RefereeScore(
                claim_id=claim.id,
                groundedness=0.0,
                falsifiability=0.0,
                survived=False,
                rationale="Placeholder de provedor — descartado.",
            )

        # LLM refusal templates ("Não posso fornecer uma resposta...",
        # "I cannot provide...", "Desculpe, não posso...", "Posso ajudar com
        # outra coisa?", etc.) are safety boilerplate, NOT evidence. They are
        # particularly common with Phi/Llama on policy-adjacent topics.
        stmt_lower = stmt.lower()[:200]
        _REFUSAL_MARKERS = (
            "não posso fornecer",
            "nao posso fornecer",
            "não posso ajudar",
            "nao posso ajudar",
            "não posso responder",
            "nao posso responder",
            "não posso atender",
            "nao posso atender",
            "desculpe, não posso",
            "desculpe, nao posso",
            "i cannot provide",
            "i can't provide",
            "i'm sorry, but i can",
            "i am sorry, but i can",
            "i cannot assist",
            "i can't assist",
            "as an ai",
            "posso ajudar com outra coisa",
            "posso ajudá-lo com outra",
            "como uma ia",
            "como ia,",
        )
        if any(marker in stmt_lower for marker in _REFUSAL_MARKERS):
            return RefereeScore(
                claim_id=claim.id,
                groundedness=0.0,
                falsifiability=0.0,
                survived=False,
                rationale="Recusa/boilerplate do LLM — descartado.",
            )

        # Degenerate statements: too short to carry an argument, or just the
        # CONCEDE sentinel emitted in the wrong turn (e.g. PROPOSE). These
        # cannot be evidence by definition.
        stripped = stmt.strip().rstrip(".!?")
        if len(stripped) < 30 or stripped.upper() == "CONCEDO":
            return RefereeScore(
                claim_id=claim.id,
                groundedness=0.0,
                falsifiability=0.0,
                survived=False,
                rationale="Statement degenerado (vazio ou apenas CONCEDO) — descartado.",
            )

        groundedness = self._score_groundedness(claim)
        falsifiability = self._score_falsifiability(claim)
        survived = (
            groundedness >= self._g_threshold
            and falsifiability >= self._f_threshold
        )
        rationale = (
            f"groundedness={groundedness:.2f} (citations={len(claim.citations)}), "
            f"falsifiability={falsifiability:.2f}, kind={claim.kind.value}"
        )
        return RefereeScore(
            claim_id=claim.id,
            groundedness=groundedness,
            falsifiability=falsifiability,
            survived=survived,
            rationale=rationale,
        )

    def _score_groundedness(self, claim: Claim) -> float:
        if not claim.citations:
            return 0.0
        avg_relevance = mean(c.relevance for c in claim.citations)
        coverage_bonus = min(len(claim.citations) / 3.0, 1.0)
        score = min(0.6 * avg_relevance + 0.4 * coverage_bonus, 1.0)
        # Penalize hard if all citations come from the keyword-overlap
        # fallback (relevance ≈ 0.15). Without this, fallback citations
        # would pump groundedness above threshold for free.
        if avg_relevance < 0.2:
            score *= 0.5
        return score

    def _score_falsifiability(self, claim: Claim) -> float:
        tokens = claim.statement.split()
        if len(tokens) < _MIN_STATEMENT_TOKENS:
            return 0.2
        lowered = f" {claim.statement.lower()} "
        marker_hits = sum(1 for m in _FALSIFIABILITY_MARKERS if m in lowered)
        base = 0.4 + 0.15 * marker_hits
        # Bonus for containing at least one explicit numeric figure — a
        # measurable claim is more falsifiable than a vague one.
        if re.search(r"\d", claim.statement):
            base += 0.1
        return min(base, 1.0)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    def aggregate(
        self, *, question: str, rounds: Sequence[DebateRound]
    ) -> DecisionDossier:
        surviving = list(_iter_surviving_claims(rounds))
        confidence, ci = _bayesian_pool(surviving)
        recommendation = _synthesize_recommendation(question, surviving, confidence, ci)
        risks = _surviving_risks(surviving)
        counterfactuals = _counterfactuals(surviving, confidence)
        return DecisionDossier(
            question=question,
            recommendation=recommendation,
            confidence=confidence,
            confidence_interval=ci,
            surviving_risks=tuple(risks),
            counterfactuals=tuple(counterfactuals),
            rounds=tuple(rounds),
        )


# ---------------------------------------------------------------------------
# Aggregation helpers (pure functions — easy to test)
# ---------------------------------------------------------------------------


def _iter_surviving_claims(rounds: Iterable[DebateRound]) -> Iterable[Claim]:
    for rnd in rounds:
        survived_ids = {s.claim_id for s in rnd.scores if s.survived}
        for c in rnd.claims:
            if c.id in survived_ids:
                yield c


def _bayesian_pool(claims: Sequence[Claim]) -> tuple[float, tuple[float, float]]:
    """Pool surviving claims into a posterior P(go-ahead) with a 95% CI.

    Uses the Beta-Binomial conjugate update with Jeffreys prior Beta(0.5, 0.5);
    each surviving claim contributes its confidence as a weighted pseudo-count
    on the side dictated by its **content stance** (not its persona). A claim
    that argues against the proposition adds mass to β regardless of who said
    it; this prevents pro/contra labelling errors when a persona's actual
    position contradicts its prior.
    """
    alpha, beta = 0.5, 0.5  # Jeffreys prior
    for c in claims:
        weight = c.confidence
        stance = _classify_stance(c)
        if stance == "for":
            alpha += weight
        elif stance == "against":
            beta += weight
        # neutral → no update (intentional: concessions and ambiguous
        # statements should widen the posterior, not bias it).
    mean_p = alpha / (alpha + beta)
    var_p = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))
    sd = math.sqrt(var_p)
    lo = max(0.0, mean_p - 1.96 * sd)
    hi = min(1.0, mean_p + 1.96 * sd)
    return mean_p, (lo, hi)


def _synthesize_recommendation(
    question: str,
    claims: Sequence[Claim],
    confidence: float,
    ci: tuple[float, float] | None = None,
) -> str:
    # Guard: when no claims survived the PCDR protocol there is no evidence
    # to base a decision on — emit an explicit inconclusiveness verdict rather
    # than a spurious "PROSSEGUIR COM RESSALVAS" driven by the Jeffreys prior.
    if not claims:
        return (
            f"EVIDÊNCIA INSUFICIENTE. "
            f"Nenhuma afirmação sobreviveu ao protocolo PCDR. "
            f"Reformule a questão com mais contexto factual sobre: {question[:200]}"
        )
    # Use the credible interval (when available) to make the verdict more
    # decisive: if the *entire* CI lies on one side of the 0.5 threshold the
    # evidence is consistent enough to commit; if the CI straddles 0.5 we hedge.
    lo, hi = (ci if ci is not None else (confidence, confidence))
    against_count = sum(1 for c in claims if _classify_stance(c) == "against")
    for_count = sum(1 for c in claims if _classify_stance(c) == "for")
    decisive_against = (
        hi <= 0.5
        or (confidence <= 0.4 and against_count >= 2 * max(for_count, 1))
    )
    decisive_for = (
        lo >= 0.5
        or (confidence >= 0.6 and for_count >= 2 * max(against_count, 1))
    )
    if decisive_against:
        verdict = "NÃO PROSSEGUIR"
    elif decisive_for:
        verdict = "PROSSEGUIR"
    else:
        verdict = "PROSSEGUIR COM RESSALVAS"
    return (
        f"{verdict}. "
        f"Decisão baseada em {len(claims)} afirmações sobreviventes ao "
        f"protocolo PCDR sobre a questão: {question[:200]}"
    )


def _surviving_risks(claims: Sequence[Claim]) -> list[str]:
    """Top-K surviving claims whose **content** opposes the proposition.

    Selection is purely stance-based — a CTO who argues against the launch
    contributes a real risk; a Customer voice who happens to agree does not
    contribute a "risk" just because of their persona label.
    Sorted by confidence so the strongest concerns surface first.
    """
    against = [
        c
        for c in claims
        if c.kind is not TurnKind.CONCEDE
        and _classify_stance(c) == "against"
    ]
    against.sort(key=lambda c: c.confidence, reverse=True)
    return [c.statement for c in against[:5]]


def _counterfactuals(
    claims: Sequence[Claim], confidence: float
) -> list[CounterfactualScenario]:
    """Build counterfactual scenarios grounded in the actual surviving evidence.

    Strategy:
      * If there are surviving against-claims, each top-K becomes a
        scenario whose probability scales with the claim's confidence
        and the inverse of overall posterior. This guarantees every
        scenario is tied to a real piece of evidence — no boilerplate.
      * If the debate produced no opposition, emit a single "decisão
        alinhada" scenario explicitly acknowledging the absence of
        falsifiers (preserves auditability of the dossier).
    """
    against = sorted(
        (
            c
            for c in claims
            if c.kind is not TurnKind.CONCEDE
            and _classify_stance(c) == "against"
        ),
        key=lambda c: c.confidence,
        reverse=True,
    )
    base_prob = max(1 - confidence, 0.0)
    scenarios: list[CounterfactualScenario] = []
    for idx, c in enumerate(against[:3]):
        statement = c.statement.strip()
        if len(statement) > 320:
            statement = statement[:317].rstrip() + "..."
        # Each successive scenario gets slightly less weight to model
        # diminishing marginal hazard from stacking risks.
        prob = round(min(base_prob * c.confidence * (1.0 - 0.15 * idx), 0.99), 2)
        if prob <= 0.05:
            continue
        condition = (
            f"Evidência de {c.persona.value} se confirma "
            f"({len(c.citations)} citação(ões))"
        )
        scenarios.append(
            CounterfactualScenario(
                description=f"A decisão falha se: {statement}",
                required_conditions=(condition,),
                probability=prob,
            )
        )
    if not scenarios:
        scenarios.append(
            CounterfactualScenario(
                description=(
                    "Nenhum risco crítico sobreviveu ao protocolo PCDR; a "
                    "decisão poderia falhar apenas se surgir evidência nova "
                    "fora do corpus auditado."
                ),
                required_conditions=("Surgimento de evidência externa não considerada",),
                probability=round(max(base_prob * 0.3, 0.05), 2),
            )
        )
    return scenarios


# ---------------------------------------------------------------------------
# Confidence calibration helper consumed by agents/base.py
# ---------------------------------------------------------------------------


def calibrated_confidence(
    citations: Sequence[Citation], *, fallback: float = 0.3
) -> float:
    """Confidence proportional to evidence quality, not just count.

    Formula: 0.3 base + 0.5 · mean(relevance) + 0.1 · coverage bonus, capped
    at 0.9. With fallback-only citations (relevance ≈ 0.15) this caps around
    0.48; with strong evidence (relevance 0.9, 3 cits) it reaches 0.85.
    """
    if not citations:
        return fallback
    avg_rel = mean(c.relevance for c in citations)
    coverage = min(len(citations) / 3.0, 1.0)
    return round(min(0.3 + 0.5 * avg_rel + 0.1 * coverage, 0.9), 4)
