"""End-to-end validation: rate-limit placeholders must NEVER leak into the
dossier as surviving_risks or counterfactuals, and the verdict text must not
contain '[Sem resposta'."""
from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

from aura.agents.referee import Referee
from aura.schemas import (
    Citation,
    Claim,
    DebateRound,
    PersonaId,
    TurnKind,
)


def mk_claim(persona: PersonaId, statement: str, kind: TurnKind = TurnKind.PROPOSE, targets: Sequence[str] = ()) -> Claim:
    return Claim(
        id=str(uuid.uuid4()),
        persona=persona,
        kind=kind,
        statement=statement,
        confidence=0.15,
        citations=[
            Citation(knowledge_source_id="ks", chunk_id=f"c{i}", excerpt="x", relevance=0.5) for i in range(3)
        ],
        targets=list(targets),
    )


def main() -> int:
    ref = Referee()

    # And one legit propose to give critique a target
    legit_propose = mk_claim(
        PersonaId.CFO, "Devemos lançar Pix com IA — ROI esperado é alto."
    )
    legit_critique = mk_claim(
        PersonaId.CFO,
        "Não devemos lançar: o impacto financeiro de downtime Pix é R$ 2M/h e excede o budget Q3.",
        kind=TurnKind.CRITIQUE,
        targets=[legit_propose.id],
    )

    claims: list[Claim] = [
        mk_claim(PersonaId.CFO, "[Sem resposta nesta rodada — rate-limit do provedor.]"),
        mk_claim(PersonaId.CTO, "[Sem resposta nesta rodada — rate-limit do provedor.]"),
        mk_claim(PersonaId.CUSTOMER, "[Sem resposta nesta rodada — rate-limit do provedor.]"),
        mk_claim(PersonaId.RED_TEAM, "[Sem resposta nesta rodada — rate-limit do provedor.]"),
        mk_claim(PersonaId.HISTORIAN, "[Sem resposta nesta rodada — rate-limit do provedor.]"),
        legit_propose,
        legit_critique,
    ]

    scores = [ref.score(c) for c in claims]
    survived_ids = {s.claim_id for s in scores if s.survived}

    # Build a fake round so we can test aggregation
    rounds = [DebateRound(index=0, turns=[], claims=claims, scores=scores)]

    dossier = ref.aggregate(
        question="Devemos lançar Pix+IA este trimestre?",
        rounds=rounds,
    )

    failures: list[str] = []

    # 1. No placeholder must survive
    for s in scores:
        c = next(c for c in claims if c.id == s.claim_id)
        if c.statement.startswith("[Sem resposta") and s.survived:
            failures.append(f"FAIL: placeholder survived: {c.id}")
        if c.statement.startswith("[Sem resposta") and (s.groundedness > 0 or s.falsifiability > 0):
            failures.append(f"FAIL: placeholder scored > 0: g={s.groundedness} f={s.falsifiability}")

    # 2. Dossier surviving_risks must not contain placeholder text
    risks_blob = " ".join(dossier.surviving_risks)
    if "[Sem resposta" in risks_blob or "rate-limit" in risks_blob:
        failures.append(f"FAIL: dossier.surviving_risks contains placeholder text:\n{risks_blob}")

    # 3. Counterfactuals must not contain placeholder text
    cf_blob = " ".join(cf.description + " " + " ".join(cf.required_conditions) for cf in dossier.counterfactuals)
    if "[Sem resposta" in cf_blob:
        failures.append(f"FAIL: dossier.counterfactuals contains placeholder:\n{cf_blob}")

    # 4. Verdict text must not contain placeholder
    if "[Sem resposta" in dossier.recommendation:
        failures.append(f"FAIL: recommendation contains placeholder: {dossier.recommendation}")

    print(f"Claims total: {len(claims)}")
    print(f"Survived: {len(survived_ids)} (expected: 0 or 1, never 5+)")
    print(f"Recommendation: {dossier.recommendation}")
    print(f"Confidence: {dossier.confidence:.3f}  CI=[{dossier.confidence_interval[0]:.2f}, {dossier.confidence_interval[1]:.2f}]")
    print(f"Surviving risks ({len(dossier.surviving_risks)}):")
    for r in dossier.surviving_risks:
        print(f"  - {r[:120]}")
    print(f"Counterfactuals ({len(dossier.counterfactuals)}):")
    for cf in dossier.counterfactuals:
        print(f"  - {cf.description[:120]}")

    if failures:
        print("\n=== FAILURES ===")
        for f in failures:
            print(f)
        return 1
    print("\n=== PASS: no placeholder pollution detected ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
