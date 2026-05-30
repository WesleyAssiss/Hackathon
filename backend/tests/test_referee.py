from __future__ import annotations

from aura.agents.referee import (
    Referee,
    _bayesian_pool,
    _classify_stance,
    _counterfactuals,
    _surviving_risks,
    audit_arithmetic,
    calibrated_confidence,
)
from aura.schemas import Citation, Claim, PersonaId, TurnKind

_ANTI_TEXT = (
    "Não devemos prosseguir porque a evidência indica risco "
    "de queda de 15% na margem operacional."
)
_PRO_TEXT = (
    "Devemos prosseguir porque a evidência indica retorno de "
    "25% em 12 meses com vantagem competitiva clara."
)


def _claim(
    persona: PersonaId,
    *,
    with_evidence: bool,
    confidence: float = 0.6,
    text: str = _ANTI_TEXT,
    kind: TurnKind = TurnKind.PROPOSE,
) -> Claim:
    citations = (
        Citation(knowledge_source_id="ks", chunk_id="c", excerpt="ev", relevance=0.9),
    ) if with_evidence else ()
    return Claim(
        persona=persona,
        kind=kind,
        statement=text,
        citations=citations,
        confidence=confidence,
    )


def test_ungrounded_claim_does_not_survive() -> None:
    score = Referee().score(_claim(PersonaId.CFO, with_evidence=False))
    assert score.survived is False
    assert score.groundedness == 0.0


def test_grounded_falsifiable_claim_survives() -> None:
    score = Referee().score(_claim(PersonaId.CFO, with_evidence=True))
    assert score.survived is True
    assert score.groundedness > 0.5
    assert score.falsifiability > 0.4


def test_bayesian_pool_against_wins_when_content_is_against() -> None:
    # All four argue against the proposition regardless of persona prior.
    claims = [
        _claim(PersonaId.CFO, with_evidence=True, confidence=0.8, text=_ANTI_TEXT),
        _claim(PersonaId.CUSTOMER, with_evidence=True, confidence=0.7, text=_ANTI_TEXT),
        _claim(PersonaId.RED_TEAM, with_evidence=True, confidence=0.9, text=_ANTI_TEXT),
        _claim(PersonaId.CTO, with_evidence=True, confidence=0.6, text=_ANTI_TEXT),
    ]
    mean_p, (lo, hi) = _bayesian_pool(claims)
    assert mean_p < 0.5
    assert 0.0 <= lo <= mean_p <= hi <= 1.0


def test_bayesian_pool_for_wins_when_content_is_for() -> None:
    claims = [
        _claim(PersonaId.CTO, with_evidence=True, confidence=0.9, text=_PRO_TEXT),
        _claim(PersonaId.HISTORIAN, with_evidence=True, confidence=0.8, text=_PRO_TEXT),
        _claim(PersonaId.CFO, with_evidence=True, confidence=0.3, text=_ANTI_TEXT),
    ]
    mean_p, _ = _bayesian_pool(claims)
    assert mean_p > 0.5


def test_stance_overrides_persona_prior() -> None:
    # CTO has 'for' prior but its actual statement opposes the proposition.
    cto_against = _claim(
        PersonaId.CTO, with_evidence=True, confidence=0.9, text=_ANTI_TEXT,
    )
    assert _classify_stance(cto_against) == "against"

    # Customer has 'against' prior but here advocates for the proposition.
    customer_for = _claim(
        PersonaId.CUSTOMER, with_evidence=True, confidence=0.9, text=_PRO_TEXT,
    )
    assert _classify_stance(customer_for) == "for"


def test_concession_classified_neutral() -> None:
    c = Claim(
        persona=PersonaId.CFO,
        kind=TurnKind.CONCEDE,
        statement="Concedo o ponto.",
        targets=(_claim(PersonaId.CTO, with_evidence=True).id,),
        confidence=0.4,
    )
    assert _classify_stance(c) == "neutral"


def test_surviving_risks_filters_by_content_stance() -> None:
    # A Customer claim that *favors* launch must NOT appear as a risk.
    pro_customer = _claim(
        PersonaId.CUSTOMER, with_evidence=True, confidence=0.9, text=_PRO_TEXT,
    )
    anti_cto = _claim(
        PersonaId.CTO, with_evidence=True, confidence=0.8, text=_ANTI_TEXT,
    )
    risks = _surviving_risks([pro_customer, anti_cto])
    assert _PRO_TEXT not in risks
    assert _ANTI_TEXT in risks


def test_counterfactuals_grounded_in_actual_evidence() -> None:
    anti = _claim(
        PersonaId.RED_TEAM, with_evidence=True, confidence=0.8, text=_ANTI_TEXT,
    )
    scenarios = _counterfactuals([anti], confidence=0.45)
    assert len(scenarios) == 1
    # Description must quote the actual claim, not a hardcoded template.
    assert "queda de 15%" in scenarios[0].description
    assert scenarios[0].probability > 0.0


def test_counterfactuals_fallback_when_no_opposition() -> None:
    pro = _claim(
        PersonaId.CTO, with_evidence=True, confidence=0.9, text=_PRO_TEXT,
    )
    scenarios = _counterfactuals([pro], confidence=0.85)
    assert len(scenarios) == 1
    desc = scenarios[0].description.lower()
    assert "evidência" in desc or "evidencia" in desc


def test_calibrated_confidence_low_for_weak_citations() -> None:
    weak = (
        Citation(knowledge_source_id="ks", chunk_id="a", excerpt="x", relevance=0.15),
        Citation(knowledge_source_id="ks", chunk_id="b", excerpt="y", relevance=0.15),
        Citation(knowledge_source_id="ks", chunk_id="c", excerpt="z", relevance=0.15),
    )
    strong = (
        Citation(knowledge_source_id="ks", chunk_id="a", excerpt="x", relevance=0.9),
        Citation(knowledge_source_id="ks", chunk_id="b", excerpt="y", relevance=0.9),
        Citation(knowledge_source_id="ks", chunk_id="c", excerpt="z", relevance=0.9),
    )
    weak_conf = calibrated_confidence(weak, fallback=0.3)
    strong_conf = calibrated_confidence(strong, fallback=0.3)
    assert weak_conf < 0.5
    assert strong_conf > 0.8
    assert strong_conf > weak_conf


def test_audit_arithmetic_flags_wrong_multiplication() -> None:
    # Forward equation form.
    forward = audit_arithmetic("Custo: 1.4M x 5 = 7.4M no trimestre")
    assert forward
    assert "1.4" in forward[0]
    # Reverse equation form ("total = a x b") — same bug, opposite syntax.
    reverse = audit_arithmetic("Burn mensal de R$ 7.4M = R$ 1.4M x 5")
    assert reverse
    assert "1.4" in reverse[0]


def test_audit_arithmetic_passes_correct_math() -> None:
    assert audit_arithmetic("Custo total = 2 x 3 = 6, dentro do orçamento.") == []


def test_audit_arithmetic_tolerates_rounding() -> None:
    # 1.4 x 5 = 7.0; reporting 7.1 is within 5% tolerance.
    assert audit_arithmetic("Aproximadamente 1.4 x 5 = 7.1 milhões") == []


def test_yes_but_classified_as_against() -> None:
    # Adversarial "concordo, mas" pattern: nominal agreement but the
    # substantive clause weakens the proposition.
    c = _claim(
        PersonaId.HISTORIAN,
        with_evidence=True,
        confidence=0.7,
        text=(
            "Concordo, mas considerando que 81% das aquisições sub-$100M "
            "falham em até 36 meses devido a dívidas de integração, é "
            "crucial reconsiderar."
        ),
    )
    assert _classify_stance(c) == "against"


def test_verb_stem_detection() -> None:
    # 'rejeito', 'compromete', 'falham' must all register as against.
    samples = [
        "Rejeito o lançamento porque a equipe é pequena.",
        "A precisão de 92% compromete o SLA exigido.",
        "Lançamentos similares falham por dívida técnica.",
    ]
    for s in samples:
        c = _claim(PersonaId.CTO, with_evidence=True, confidence=0.7, text=s)
        assert _classify_stance(c) == "against", f"failed for: {s!r}"


def test_cto_historian_priors_are_neutral() -> None:
    # When content is neutral the classifier must NOT inject a directional
    # prior for CTO/Historian — they argue both sides depending on the topic.
    neutral_text = "A questão demanda mais dados antes de uma conclusão."
    cto = _claim(PersonaId.CTO, with_evidence=True, confidence=0.5, text=neutral_text)
    historian = _claim(
        PersonaId.HISTORIAN, with_evidence=True, confidence=0.5, text=neutral_text,
    )
    assert _classify_stance(cto) == "neutral"
    assert _classify_stance(historian) == "neutral"


def test_provider_fallback_never_survives() -> None:
    # Rate-limit / content-filter placeholders must be filtered out of the
    # dossier — they have no informational content and would otherwise leak
    # into surviving_risks and pollute the posterior.
    fallback_a = _claim(
        PersonaId.CTO,
        with_evidence=True,
        confidence=0.15,
        text="[Sem resposta nesta rodada — rate-limit do provedor.]",
    )
    fallback_b = _claim(
        PersonaId.CFO,
        with_evidence=True,
        confidence=0.15,
        text="[Resposta vazia do provedor — sem evidência adicional.]",
    )
    ref = Referee()
    assert ref.score(fallback_a).survived is False
    assert ref.score(fallback_b).survived is False

