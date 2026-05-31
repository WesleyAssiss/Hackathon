"""Generate architecture diagram PNG via mermaid.ink API."""
import base64
import urllib.request
import pathlib

mermaid_code = """flowchart TD
    subgraph CLIENT[" Client Layer "]
        WR["War Room Browser"]
        BOT["Discord Bot /debate command"]
    end

    subgraph API[" API Layer - FastAPI "]
        GRD1["Injection Guard 1 HTTP boundary"]
        SSE["SSE Stream /debates endpoint"]
    end

    subgraph ORCH[" Orchestrator - PCDR-Loop "]
        direction LR
        P1["CFO"]
        P2["CTO"]
        P3["Customer Voice"]
        P4["Red-Team"]
        P5["Historian"]
    end

    subgraph IQ[" Microsoft Foundry IQ - Required "]
        AIS["Azure AI Search Persona-scoped knowledge queries"]
        GRD2["Injection Guard 2 + PII Redactor Presidio"]
    end

    subgraph LLM[" LLM Layer "]
        AOAI["Azure OpenAI GPT-4.1 Managed Identity"]
        GHM["GitHub Models GPT-4o - Llama-3.3-70B fallback free tier"]
    end

    subgraph REF[" Bayesian Referee "]
        BB["Beta-Binomial Jeffreys Prior CI 95pct"]
        DOS["Decision Dossier Recommendation plus Risks plus Citations"]
    end

    subgraph OBS[" Observability "]
        AI["App Insights + OpenTelemetry structlog"]
    end

    WR -->|"POST /debates"| GRD1
    BOT -->|"POST /debates"| GRD1
    GRD1 --> SSE
    SSE --> P1
    SSE --> P2
    SSE --> P3
    SSE --> P4
    SSE --> P5
    P1 -->|"persona-scoped query"| AIS
    P2 -->|"persona-scoped query"| AIS
    P3 -->|"persona-scoped query"| AIS
    P4 -->|"persona-scoped query"| AIS
    P5 -->|"persona-scoped query"| AIS
    AIS --> GRD2
    GRD2 -->|"sanitized chunks"| P1
    GRD2 -->|"sanitized chunks"| P2
    GRD2 -->|"sanitized chunks"| P3
    GRD2 -->|"sanitized chunks"| P4
    GRD2 -->|"sanitized chunks"| P5
    P1 -->|"prompt"| AOAI
    P2 -->|"prompt"| AOAI
    P3 -->|"prompt"| AOAI
    P4 -->|"prompt"| AOAI
    P5 -->|"prompt"| AOAI
    AOAI -->|"fallback"| GHM
    P1 --> BB
    P2 --> BB
    P3 --> BB
    P4 --> BB
    P5 --> BB
    BB --> DOS
    DOS -->|"SSE events stream"| WR
    DOS -->|"formatted embed"| BOT
    SSE -.->|"telemetry"| AI

    style IQ fill:#0050a0,color:#fff,stroke:#0078d4,stroke-width:4px
    style ORCH fill:#1e1e2e,color:#fff,stroke:#7c3aed,stroke-width:2px
    style REF fill:#1e2e1e,color:#fff,stroke:#16a34a,stroke-width:2px
    style API fill:#2e1e1e,color:#fff,stroke:#dc2626,stroke-width:2px
    style CLIENT fill:#2e2a1e,color:#fff,stroke:#d97706,stroke-width:2px
    style LLM fill:#1e2530,color:#fff,stroke:#0ea5e9,stroke-width:2px
    style OBS fill:#1e1e1e,color:#ccc,stroke:#6b7280,stroke-width:1px
"""

encoded = base64.urlsafe_b64encode(mermaid_code.encode("utf-8")).decode("ascii")
url = f"https://mermaid.ink/img/{encoded}"

print(f"URL length: {len(url)}")
print("Downloading from mermaid.ink...")
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    out = pathlib.Path("docs/architecture.png")
    out.write_bytes(data)
    print(f"Saved: {out} ({len(data):,} bytes)")
except Exception as e:
    print(f"Error: {e}")
    raise
