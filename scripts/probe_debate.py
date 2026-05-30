"""Tiny SSE consumer for /debates — prints the final dossier as JSON.

Usage: python scripts/probe_debate.py
"""
from __future__ import annotations

import json
import sys
import urllib.request

REQ = {
    "question": "Devemos lançar o pagamento via Pix com IA fraud-detection em produção este trimestre?",
    "context": "Equipe enxuta de 4 engenheiros. Modelo de IA validado offline com 92% precisão mas zero shadow-mode. SLA Pix exige 99.95% uptime.",
    "mode": "free",
    "max_rounds": 3,
}


def main() -> int:
    body = json.dumps(REQ).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/debates",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    claims: list[dict] = []
    dossier: dict | None = None
    with urllib.request.urlopen(req, timeout=180) as resp:
        ev_name = None
        data_lines: list[str] = []
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line.startswith("event:"):
                ev_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
            elif line == "":
                if ev_name and data_lines:
                    try:
                        payload = json.loads("".join(data_lines))
                    except json.JSONDecodeError:
                        payload = {"raw": "".join(data_lines)}
                    if ev_name == "claim_emitted":
                        c = payload.get("payload", payload)
                        claims.append(c)
                        print(
                            f"  [{c.get('persona')}/{c.get('kind')}] "
                            f"conf={c.get('confidence'):.2f} "
                            f"cit={len(c.get('citations', []))} "
                            f"-- {c.get('statement', '')[:120]}",
                            flush=True,
                        )
                    elif ev_name == "dossier":
                        dossier = payload
                ev_name = None
                data_lines = []

    if dossier is None:
        print("NO DOSSIER", file=sys.stderr)
        return 1
    print("\n=== DOSSIER ===")
    print(f"Recommendation: {dossier['recommendation']}")
    print(f"Confidence: {dossier['confidence']:.3f}  CI: {dossier['confidence_interval']}")
    print("Surviving risks:")
    for r in dossier["surviving_risks"]:
        print(f"  - {r[:200]}")
    print("Counterfactuals:")
    for c in dossier["counterfactuals"]:
        print(f"  - p={c['probability']}  {c['description'][:200]}")
    # Quick assertions for audit
    confs = [round(c.get("confidence", 0), 2) for c in claims if c.get("kind") == "propose"]
    print(f"\nPropose confidences: {confs}  (uniqueness: {len(set(confs))}/{len(confs)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
