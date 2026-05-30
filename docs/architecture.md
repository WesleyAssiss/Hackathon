# AURA — Arquitetura

## Visão geral

```mermaid
flowchart LR
    U[Usuário<br/>War Room] -->|POST /debates SSE| API[FastAPI<br/>injection guard]
    API --> ORCH[Orchestrator<br/>PCDR-Loop]
    ORCH -->|fan-out| P1[CFO]
    ORCH --> P2[CTO]
    ORCH --> P3[Voz do Cliente]
    ORCH --> P4[Red-Team]
    ORCH --> P5[Historiador]
    P1 & P2 & P3 & P4 & P5 -->|claims + citations| REF[Referee Bayesiano<br/>Beta-Binomial pool]
    P1 & P2 & P3 & P4 & P5 -.->|persona-scoped query| KS[(Foundry IQ<br/>Azure AI Search)]
    P1 & P2 & P3 & P4 & P5 -.->|prompt| LLM[(Azure OpenAI<br/>GPT-4.1)]
    KS -.->|chunks| GUARD[injection guard #2<br/>PII redactor]
    GUARD -.-> P1 & P2 & P3 & P4 & P5
    REF --> DOS[Decision Dossier<br/>recommendation + CI95%]
    DOS -->|SSE event: dossier| U
    API -.->|telemetry| OTEL[App Insights]
```

## Componentes

| Camada              | Implementação                                                    |
|---------------------|------------------------------------------------------------------|
| API                 | FastAPI + sse-starlette                                          |
| Orchestrator        | `aura.orchestrator.Orchestrator` (PCDR-Loop, early-stop entropia)|
| Personas            | `aura.personas.default_council()` (5 agentes)                    |
| Referee             | `aura.referee.Referee` (Beta-Binomial, prior de Jeffreys)        |
| Knowledge           | `aura.knowledge.FoundryIQClient` (Azure AI Search backend)       |
| LLM                 | `aura.llm.AzureOpenAIClient` (Managed Identity)                  |
| Segurança           | `aura.safety.injection` + `aura.safety.redact` (Presidio)        |
| Observability       | structlog + OTel + App Insights                                  |
| Deploy              | Container Apps + Bicep (`azd up`)                                |

## PCDR-Loop

```mermaid
sequenceDiagram
    participant U as Usuário
    participant O as Orchestrator
    participant P as Persona N
    participant R as Referee
    U->>O: question
    loop até max_rounds ou entropia < ε
        O->>P: PROPOSE
        P-->>O: claim + citations
        O->>P: CRITIQUE (cross-persona)
        P-->>O: critique
        O->>P: DEFEND
        P-->>O: defense
        O->>P: REFINE
        P-->>O: refined claim
        O->>R: score(claim)
        R-->>O: Beta posterior update
    end
    O->>R: build_dossier()
    R-->>U: DecisionDossier (SSE)
```

## Segurança — defense in depth

1. **Injection guard #1** no boundary HTTP (`POST /debates`).
2. **Injection guard #2** após cada fetch de Knowledge (instrução vinda de doc envenenado).
3. **PII redactor** (Presidio) em outputs antes da emissão SSE.
4. **Suite Red-Team** (43 prompts) executada no CI — falha o build se block-rate < 90%.
