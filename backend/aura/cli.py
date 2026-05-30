"""AURA Demo CLI.

Runs a full debate end-to-end in mock mode and prints a cinematic
terminal transcript of the PCDR-Loop, ending with the rendered
DecisionDossier. Used both for development dogfooding and for the
fallback path of the pitch demo (in case the live UI breaks on stage).

Usage:
    python -m aura.cli "Devemos adquirir a startup ACME por $50M?"
    python -m aura.cli --question "..." --rounds 2 --context "contexto..."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import textwrap
from collections.abc import Iterable

# Force UTF-8 on Windows consoles so ANSI box-drawing + emoji glyphs render.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

from aura.agents import Orchestrator, Referee, default_council
from aura.factory import build_knowledge, build_llm
from aura.observability import bind_trace_id, configure_logging, new_trace_id
from aura.schemas import (
    DecisionDossier,
    PersonaId,
    StreamEvent,
    StreamEventKind,
    TurnKind,
)

# ANSI cinematic palette --------------------------------------------------
RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
PERSONA_COLOR = {
    PersonaId.CFO: "\x1b[38;5;39m",        # azure
    PersonaId.CTO: "\x1b[38;5;208m",       # orange
    PersonaId.CUSTOMER: "\x1b[38;5;141m",  # purple
    PersonaId.RED_TEAM: "\x1b[38;5;196m",  # red
    PersonaId.HISTORIAN: "\x1b[38;5;220m", # gold
}
KIND_GLYPH = {
    TurnKind.PROPOSE: "◆",
    TurnKind.CRITIQUE: "✕",
    TurnKind.DEFEND: "▲",
    TurnKind.CONCEDE: "~",
}


def _color_supported() -> bool:
    return sys.stdout.isatty()


def _c(code: str) -> str:
    return code if _color_supported() else ""


def _render_event(ev: StreamEvent) -> str | None:
    if ev.kind == StreamEventKind.ROUND_STARTED:
        rnd = ev.payload["round"]
        bar = "─" * 40
        return f"\n{_c(BOLD)}{bar} ROUND {rnd} {bar}{_c(RESET)}"
    if ev.kind == StreamEventKind.CLAIM_EMITTED:
        p = PersonaId(ev.payload["persona"])
        kind = TurnKind(ev.payload["kind"])
        glyph = KIND_GLYPH.get(kind, "·")
        statement = textwrap.fill(
            ev.payload["statement"], width=88, subsequent_indent="     "
        )
        cites = len(ev.payload["citations"])
        conf = ev.payload["confidence"]
        return (
            f"  {_c(PERSONA_COLOR[p])}{glyph} {p.value.upper():<9}{_c(RESET)} "
            f"{_c(DIM)}[{kind.value} · conf={conf:.2f} · cites={cites}]{_c(RESET)}\n"
            f"     {statement}"
        )
    if ev.kind == StreamEventKind.SCORE_EMITTED:
        ok = "✓" if ev.payload["survived"] else "✗"
        return (
            f"     {_c(DIM)}referee {ok} g={ev.payload['groundedness']:.2f} "
            f"f={ev.payload['falsifiability']:.2f}{_c(RESET)}"
        )
    return None


def _render_dossier(d: DecisionDossier) -> str:
    lo, hi = d.confidence_interval
    bar = "═" * 88
    lines: list[str] = [
        f"\n{_c(BOLD)}{bar}{_c(RESET)}",
        f"{_c(BOLD)}  DECISION DOSSIER · {d.debate_id}{_c(RESET)}",
        f"{_c(BOLD)}{bar}{_c(RESET)}",
        "",
        f"  Question:        {d.question}",
        f"  Recommendation:  {_c(BOLD)}{d.recommendation}{_c(RESET)}",
        f"  Confidence:      {d.confidence:.0%}  (95% CI [{lo:.0%}, {hi:.0%}])",
        "",
        "  Surviving risks:",
    ]
    lines.extend(f"    • {r[:200]}" for r in d.surviving_risks) or lines.append("    (none)")
    lines.append("")
    lines.append("  Counterfactual scenarios:")
    for cf in d.counterfactuals:
        lines.append(f"    • [{cf.probability:.0%}] {cf.description}")
        for cond in cf.required_conditions:
            lines.append(f"        - requires: {cond}")
    lines.append(f"\n{_c(BOLD)}{bar}{_c(RESET)}")
    return "\n".join(lines)


async def run(question: str, *, rounds: int, mode: str, context: str | None) -> int:
    configure_logging(level="WARNING")
    bind_trace_id(new_trace_id())
    llm = build_llm(mode)  # type: ignore[arg-type]
    knowledge = build_knowledge(mode)  # type: ignore[arg-type]
    agents = default_council(llm=llm, knowledge=knowledge)
    orchestrator = Orchestrator(agents=agents, referee=Referee(), max_rounds=rounds)

    dossier: DecisionDossier | None = None
    async for item in orchestrator.run(question=question, context=context):
        if isinstance(item, StreamEvent):
            rendered = _render_event(item)
            if rendered:
                print(rendered, flush=True)
        else:
            dossier = item

    if dossier is None:
        print("ERROR: no dossier produced", file=sys.stderr)
        return 2
    print(_render_dossier(dossier))
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", help="The strategic decision to debate")
    parser.add_argument("--question", dest="q_opt", help=argparse.SUPPRESS)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--mode", choices=("mock", "free", "azure"), default="mock")
    parser.add_argument("--context", default=None)
    parser.add_argument("--json", action="store_true", help="Emit dossier as JSON only")
    args = parser.parse_args(list(argv) if argv is not None else None)
    question = args.question or args.q_opt
    if not question:
        parser.error("Provide a question (positional or --question)")
    if args.json:
        async def _run_json() -> int:
            llm = build_llm(args.mode)
            knowledge = build_knowledge(args.mode)
            agents = default_council(llm=llm, knowledge=knowledge)
            orch = Orchestrator(agents=agents, referee=Referee(), max_rounds=args.rounds)
            async for item in orch.run(question=question, context=args.context):
                if isinstance(item, DecisionDossier):
                    print(json.dumps(json.loads(item.model_dump_json()), indent=2))
                    return 0
            return 2
        return asyncio.run(_run_json())
    return asyncio.run(run(question, rounds=args.rounds, mode=args.mode, context=args.context))


if __name__ == "__main__":
    raise SystemExit(main())
