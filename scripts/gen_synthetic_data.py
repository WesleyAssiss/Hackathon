"""Deterministic synthetic dataset generator for AURA Knowledge Sources.

Output is committed under `data/synthetic/` and consumed by the in-memory
Knowledge client (D1) and the Foundry IQ ingestion script (D2).

Determinism rules:
    * Seed is fixed (`42`) and recorded in the file header.
    * Output is JSONL, sorted by `chunk_id`.
    * Every record carries a SHA-256 of its `text` field for tamper-evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parents[1] / "data" / "synthetic"


@dataclass(frozen=True, slots=True)
class Record:
    knowledge_source_id: str
    chunk_id: str
    persona: str
    text: str
    keywords: list[str]
    text_sha256: str

    @classmethod
    def make(
        cls,
        knowledge_source_id: str,
        chunk_id: str,
        persona: str,
        text: str,
        keywords: list[str],
    ) -> Record:
        return cls(
            knowledge_source_id=knowledge_source_id,
            chunk_id=chunk_id,
            persona=persona,
            text=text,
            keywords=sorted(set(keywords)),
            text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )


COMPANIES = (
    "ACME", "ZenithAI", "Helios", "NimbusCorp", "Orbital", "VertexLabs",
    "Polaris", "Solstice", "Atlas", "Quantum",
)

CFO_TEMPLATES = (
    (
        "{co} Q{q} {year} financials (synthetic): monthly burn ${burn}M, "
        "runway {run}m, gross margin {margin}%."
    ),
    "{co} synthetic ARR: ${arr}M with {growth}% YoY growth and {churn}% revenue churn.",
)
CTO_TEMPLATES = (
    "{co} stack (synthetic): {lang} + {db} + {bus}; estimated roadmap acceleration {accel} months.",
    "{co} platform debt index (synthetic) is {debt}/10; deployment frequency {dep}/day.",
)
CUSTOMER_TEMPLATES = (
    "{co} synthetic review corpus: NPS {nps}, churn {churn}%, top complaint: {complaint}.",
)
RED_TEAM_TEMPLATES = (
    "{cve} affects a component used by {co}; CVSS {cvss}; patch available in v{patch}.",
)
HISTORIAN_TEMPLATES = (
    (
        "Public failure-pattern study: {rate}% of sub-${cap}M acquisitions "
        "fail within {win} months due to {cause}."
    ),
)


def _gen_cfo(rng: random.Random) -> list[Record]:
    out: list[Record] = []
    for co in COMPANIES:
        for tpl in CFO_TEMPLATES:
            text = tpl.format(
                co=co,
                q=rng.randint(1, 4),
                year=rng.choice((2024, 2025, 2026)),
                burn=round(rng.uniform(0.5, 5.0), 1),
                run=rng.randint(6, 36),
                margin=rng.randint(15, 55),
                arr=round(rng.uniform(2, 80), 1),
                growth=rng.randint(-10, 120),
                churn=rng.randint(2, 30),
            )
            chunk_id = f"cfo-{co.lower()}-{abs(hash(text)) % 10_000:04d}"
            out.append(
                Record.make(
                    knowledge_source_id="synthetic_market_reports",
                    chunk_id=chunk_id,
                    persona="cfo",
                    text=text,
                    keywords=[co.lower(), "financials", "burn", "runway", "margin", "arr"],
                )
            )
    return out


def _gen_cto(rng: random.Random) -> list[Record]:
    langs = ("Rust", "Go", "Python", "TypeScript", "Java")
    dbs = ("Postgres", "CosmosDB", "DynamoDB", "Spanner", "MySQL")
    buses = ("Kafka", "EventHubs", "NATS", "Pulsar", "RabbitMQ")
    out: list[Record] = []
    for co in COMPANIES:
        for tpl in CTO_TEMPLATES:
            text = tpl.format(
                co=co,
                lang=rng.choice(langs),
                db=rng.choice(dbs),
                bus=rng.choice(buses),
                accel=rng.randint(3, 24),
                debt=rng.randint(2, 9),
                dep=rng.randint(1, 50),
            )
            out.append(
                Record.make(
                    knowledge_source_id="synthetic_company_tech_stacks",
                    chunk_id=f"cto-{co.lower()}-{abs(hash(text)) % 10_000:04d}",
                    persona="cto",
                    text=text,
                    keywords=[co.lower(), "stack", "platform", "roadmap"],
                )
            )
    return out


def _gen_customer(rng: random.Random) -> list[Record]:
    complaints = ("onboarding friction", "unreliable SLAs", "weak documentation", "poor support")
    return [
        Record.make(
            knowledge_source_id="synthetic_g2_reviews",
            chunk_id=f"cust-{co.lower()}-{i:02d}",
            persona="customer",
            text=CUSTOMER_TEMPLATES[0].format(
                co=co,
                nps=rng.randint(-40, 60),
                churn=rng.randint(5, 45),
                complaint=rng.choice(complaints),
            ),
            keywords=[co.lower(), "nps", "churn", "reviews", "customer"],
        )
        for i, co in enumerate(COMPANIES)
    ]


def _gen_red_team(rng: random.Random) -> list[Record]:
    return [
        Record.make(
            knowledge_source_id="nvd_cve_subset",
            chunk_id=f"cve-{2024 + i % 3}-{rng.randint(1000, 9999)}",
            persona="red_team",
            text=RED_TEAM_TEMPLATES[0].format(
                cve=f"CVE-{2024 + i % 3}-{rng.randint(1000, 9999)}",
                co=co,
                cvss=round(rng.uniform(5.0, 9.9), 1),
                patch=f"{rng.randint(1, 4)}.{rng.randint(0, 9)}",
            ),
            keywords=[co.lower(), "cve", "vulnerability", "patch"],
        )
        for i, co in enumerate(COMPANIES)
    ]


def _gen_historian(rng: random.Random) -> list[Record]:
    causes = (
        "cultural mismatch",
        "integration debt",
        "key-talent attrition",
        "regulatory blockers",
    )
    return [
        Record.make(
            knowledge_source_id="hbr_failure_patterns",
            chunk_id=f"hist-{i:03d}",
            persona="historian",
            text=HISTORIAN_TEMPLATES[0].format(
                rate=rng.randint(55, 85),
                cap=rng.choice((50, 100, 250)),
                win=rng.choice((18, 24, 36)),
                cause=rng.choice(causes),
            ),
            keywords=["acquisition", "failure", "integration", "history"],
        )
        for i in range(len(COMPANIES))
    ]


def generate() -> dict[str, list[Record]]:
    rng = random.Random(SEED)
    return {
        "cfo": _gen_cfo(rng),
        "cto": _gen_cto(rng),
        "customer": _gen_customer(rng),
        "red_team": _gen_red_team(rng),
        "historian": _gen_historian(rng),
    }


def write(out_root: Path) -> dict[str, int]:
    out_root.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for persona, records in generate().items():
        path = out_root / f"{persona}.jsonl"
        records_sorted = sorted(records, key=lambda r: r.chunk_id)
        with path.open("w", encoding="utf-8") as fh:
            for r in records_sorted:
                fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
        counts[persona] = len(records_sorted)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT, help="Output directory")
    args = parser.parse_args()
    counts = write(args.out)
    for persona, n in counts.items():
        print(f"  {persona:>10}  {n:>3} records")
    print(f"Total: {sum(counts.values())} records → {args.out}")


if __name__ == "__main__":
    main()
