# AURA — Hackathon Submission Text
*Innovation Studio · Agents League 2026 · Preencher em: 4 de junho de 2025*

---

## 📌 Project Name
```
AURA — Adversarial Unified Reasoning Arena
```

---

## 📝 Short Description (~280 characters)
```
AURA assembles a 5-agent AI council that adversarially debates strategic questions using the PCDR-Loop protocol. A Bayesian Referee emits a Decision Dossier with 95% CI, surviving risks, and 16× more citations. Powered by Microsoft Foundry IQ (Azure AI Search).
```

---

## 📄 Full Description (para os juízes)

```
AURA solves the sycophancy problem in LLMs: frontier models agree with users, emit mono-perspective answers, and hide their confidence levels. AURA inverts this by convening a Synthetic Council of 5 AI agents—CFO, CTO, Customer Voice, Red-Team, and Historian—with conflicting incentives and mental models.

HOW IT WORKS:
1. User submits a strategic question via the War Room (browser) or Discord /debate command
2. An Injection Guard validates and sanitizes the input at the HTTP boundary
3. The PCDR-Loop Orchestrator (asyncio fan-out) activates all 5 agents in parallel
4. Each agent queries Microsoft Foundry IQ (Azure AI Search) with persona-scoped filters:
   - CFO → financial precedents and cost benchmarks
   - Red-Team → failure cases and adversarial scenarios
   - Historian → historical analogues and case studies
5. Agents execute 4 structured rounds: Propose → Critique → Defend → Refine
   Early stopping triggers when entropy H < 0.35 (convergence detected)
6. A Bayesian Referee (Beta-Binomial model, Jeffreys Prior) scores each surviving claim
7. Output: Decision Dossier with recommendation, 95% credibility interval, surviving risks, and anchored citations streamed via SSE

MICROSOFT IQ INTEGRATION:
Foundry IQ (Azure AI Search) is the primary knowledge layer for every agent. Each persona queries with role-specific filters, retrieving only contextually relevant documents. Implemented in backend/aura/knowledge/foundry_iq_azure.py. Free-tier fallback uses GitHub Models (GPT-4o / Llama-3.3-70B) via github_models_knowledge.py.

SECURITY:
- 2× injection guard layers (HTTP boundary + knowledge retrieval)
- PII Redactor powered by Presidio
- Red-Team CI suite: 43 adversarial attack patterns, ≥90% block rate, 0 false positives
- Azure Managed Identity for OpenAI (no credentials in environment variables)

RESULTS vs SINGLE-AGENT BASELINE:
- 4× more risk dimensions identified
- 16× more cited sources per decision
- 89/89 tests passing (unit + integration + red-team)
- ≥90% adversarial prompt block rate

DEPLOYMENT:
- Azure Container Apps (azd up — one command deployment)
- Azure OpenAI GPT-4.1 (primary LLM)
- Application Insights + OpenTelemetry (observability)
- Free tier: GitHub Models, no Azure required
```

---

## 🏷️ Track
```
Primary:   Reasoning Agents
Secondary: Creative Apps
```

---

## 🔗 GitHub Repository
```
https://github.com/WesleyAssiss/Hackathon
```

---

## 🖼️ Architecture Diagram URL
```
https://raw.githubusercontent.com/WesleyAssiss/Hackathon/Principal/docs/architecture.png
```

---

## 🛠️ Technologies Used
```
Python 3.11+
FastAPI
Microsoft Foundry IQ (Azure AI Search)
Azure OpenAI GPT-4.1
GitHub Models (GPT-4o / Llama-3.3-70B)
Azure Container Apps
Azure Managed Identity
Azure Application Insights
OpenTelemetry
Microsoft Presidio (PII Redaction)
vis-network (debate graph visualization)
Discord.py
asyncio (fan-out orchestration)
pytest (89 tests)
```

---

## ✨ Key Differentiators
```
1. Adversarial multi-agent debate (not parallel consensus) — agents have conflicting incentives
2. PCDR-Loop with entropy-based early stopping (H < 0.35)
3. Bayesian Referee with 95% credibility interval output
4. Persona-scoped Microsoft Foundry IQ queries — each agent gets role-filtered knowledge
5. 2-layer security: HTTP injection guard + knowledge-layer PII redaction
6. Live graph visualization: debate network with surviving/defeated nodes colored by persona
7. Free-tier mode: full functionality without Azure (GitHub Models fallback)
```

---

## 📊 Metrics Table (para incluir em campo de descrição adicional)
```
Metric                        | AURA    | Single-Agent Baseline
------------------------------|---------|----------------------
Risk dimensions identified    | 4×      | 1×
Citations per decision        | 16×     | 1×
Adversarial prompt block rate | ≥ 90%   | N/A
False positive rate           | 0%      | N/A
Test coverage                 | 89/89   | N/A
Confidence output             | 95% CI  | None
```

---

## 🎬 Video Demo Script (quando gravar — max 5 min)
```
0:00–0:30  Problema: mostrar um LLM comum concordando com uma premissa falsa
0:30–1:30  War Room: digitar pergunta estratégica, ver 5 agentes debatendo ao vivo
           - Mostrar o grafo visual com arestas ⚔ refuta / 🛡 defende / ✋ concede
           - Mostrar personas coloridas no sidebar
1:30–2:30  Decision Dossier: recomendação final, CI 95%, riscos sobreviventes, citações
2:30–3:00  Discord bot: comando /debate, embed formatado
3:00–4:00  Código: foundry_iq_azure.py — persona-scoped Azure AI Search queries
           - Mostrar o filtro por role na query
4:00–5:00  Diagrama de arquitetura + métricas: 4× riscos, 16× citações, 89/89 testes
           - "One command deploy: azd up"
```

---

## 📎 Assets
| Asset | Path | URL |
|-------|------|-----|
| Architecture diagram | `docs/architecture.png` | https://raw.githubusercontent.com/WesleyAssiss/Hackathon/Principal/docs/architecture.png |
| README | `README.md` | https://github.com/WesleyAssiss/Hackathon/blob/Principal/README.md |
| Foundry IQ integration | `backend/aura/knowledge/foundry_iq_azure.py` | https://github.com/WesleyAssiss/Hackathon/blob/Principal/backend/aura/knowledge/foundry_iq_azure.py |
| Frontend War Room | `frontend/index.html` | https://github.com/WesleyAssiss/Hackathon/blob/Principal/frontend/index.html |
