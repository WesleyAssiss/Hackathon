# AURA — Pitch Deck (3 minutos)

> Cada `---` é um slide. Use Marp, slides.com ou PowerPoint.

---

## 1. Abertura (15s)

# AURA
### Adversarial Unified Reasoning Arena

> *"Por que pedir 1 resposta a 1 modelo quando você pode arbitrar 5 modelos especialistas que discordam entre si?"*

Liga dos Agentes 2026 — Trilha **Reasoning Agents (Microsoft Foundry)**

---

## 2. O problema (20s)

LLMs de fronteira **alucinam com confiança**. Decisões estratégicas exigem **dissenso estruturado**, não consenso plástico.

- Respostas monocromáticas, sem visão de risco
- Zero auditabilidade ("o GPT disse")
- Vulneráveis a prompt injection direta e indireta
- Sem calibração — não sabemos *quanto* confiar

---

## 3. A solução (25s)

AURA é um **Conselho de Agentes** que debate adversarialmente sua decisão estratégica usando o protocolo **PCDR-Loop** (Propose → Critique → Defend → Refine).

| Persona        | Papel                                          |
|----------------|------------------------------------------------|
| CFO            | Disciplina financeira, FCF, runway             |
| CTO            | Viabilidade técnica, dívida arquitetural       |
| Voz do Cliente | NPS, churn, friction                           |
| Red-Team       | Ataque adversarial obrigatório                 |
| Historiador    | Casos históricos comparáveis (lições)          |

Um **Referee Bayesiano** agrega votos e emite um **Decision Dossier** assinado.

---

## 4. Por que é inovador (30s)

1. **Pool Bayesiano** com prior de Jeffreys Beta(0.5, 0.5) → confiança posterior calibrada com **intervalo de credibilidade 95%**. Não é "85%" chutado, é estatisticamente derivado.
2. **Early-stop por entropia** → para quando o conselho converge (eficiência de tokens).
3. **Defense-in-depth tripla** contra prompt injection (regex no API + após Knowledge fetch + Presidio PII redactor) com **suite Red-Team de 43 ataques** automatizada no CI.
4. **War Room ao vivo** com argument graph em vis-network — você *vê* o debate.
5. **100% dados sintéticos** com SHA-256 por chunk — zero risco regulatório.

---

## 5. Stack Microsoft (15s)

- **Reasoning**: Azure OpenAI GPT-4.1 via Managed Identity
- **Knowledge**: Foundry IQ (Azure AI Search) com filtro por persona
- **Observability**: App Insights + structlog + trace contextvar
- **Deploy**: Container Apps + Bicep + `azd up`
- **Segurança**: MI + injection guard + PII redactor

Trilha: Reasoning Agents — Foundry IQ obrigatório **usado**.

---

## 6. Prova quantitativa (20s)

`scripts/baseline_harness.py` mede AURA vs single-agent no mesmo prompt:

| Métrica                     | Single GPT | AURA     | Δ      |
|-----------------------------|------------|----------|--------|
| Dimensões de risco          | 1          | 4        | **4×** |
| Citations grounded          | 0          | 16       | **∞**  |
| Adversarial coverage        | nao        | sim      | —      |
| Auditable dossier (CI 95%)  | nao        | sim      | —      |

Red-Team Suite: **>90% block rate** em 43 ataques, **0 falsos positivos** em 10 prompts limpos.

---

## 7. Demo (45s)

1. War Room abre: 3 colunas (Pergunta · Debate ao vivo · Dossier).
2. Pergunta: *"Devemos adquirir a ACME por R$ 50M para acelerar entrada no mercado brasileiro?"*
3. Vemos claims chegando, Red-Team atacando, Historiador citando casos.
4. Claims que sobrevivem ficam **verdes**. Referee emite veredito com CI.
5. Dossier final: recomendação + confiança + riscos sobreviventes + assinatura.

---

## 8. Próximos passos (10s)

- Multi-LLM heterogêneo (GPT-4o + Sonnet + Llama) para diversidade epistêmica real.
- Discord/Teams bot para vote-by-react (já scaffold em `backend/aura_bot/`).
- Vertical packs: M&A, regulatório, compliance.

**Obrigado.** Repo: `github.com/<você>/aura` — `azd up` reproduz tudo.
