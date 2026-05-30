"""AURA Council Bot — Discord MVP for the viral "community vote" driver.

Posts the live debate dossier to a channel and collects 👍 / 👎 reactions
as a lightweight crowd-vote signal alongside the Bayesian Referee.

Run:
    pip install -e ".[bot]"
    $env:DISCORD_BOT_TOKEN = "<token>"
    $env:AURA_API_BASE     = "https://<your-app>.azurecontainerapps.io"
    python -m aura_bot

Slash commands:
    /debate question:"Devemos adquirir a ACME por 50M?" rounds:3
"""

from __future__ import annotations

import json
import os
import re

import discord  # type: ignore[import-not-found]
import httpx
from discord import app_commands  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# Limpa linguagem de debate interno dos agentes antes de exibir ao usuário.
# Agentes usam frases como "Concordo, mas...", "Mantenho a posição porque..."
# que fazem sentido no debate mas confundem um leigo no resultado final.
# ---------------------------------------------------------------------------
_RISK_META_RE = re.compile(
    r"^\s*("
    r"Concordo(?:\s*com isso)?[,;]?\s*(?:mas\s*)?(?:é importante notar que\s*|que\s*)?"
    r"|Discordo(?:\s*com isso)?[,;]?\s*(?:pois\s*|porque\s*|mas\s*)?"
    r"|Mantenho (?:a|minha) posição[,;]?\s*(?:porque\s*|pois\s*)?"
    r"|Devemos (?:rejeitar|apoiar)[^,;]+[,;]\s*"
    r"|Afirmo que\s*"
    r"|Considero que\s*"
    r")",
    re.IGNORECASE,
)


def _strip_meta(text: str) -> str:
    """Remove linguagem de debate interno e retorna afirmação limpa."""
    import re as _re
    cleaned = _RISK_META_RE.sub("", text)
    cleaned = _re.sub(r'^["\'.,;:\-\s\u2026\.]+', "", cleaned).strip()
    if len(cleaned) < 20:
        return text  # muito curto após strip, mantém original
    return cleaned[0].upper() + cleaned[1:]

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

API_BASE = os.environ.get("AURA_API_BASE", "http://localhost:8000")
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def _format_progress(claims: int, survived: int, conf: float | None) -> str:
    lines = [
        "🟦 **AURA Council** — debate em andamento…",
        f"Claims emitidas: **{claims}** · sobreviventes: **{survived}**",
    ]
    if conf is not None:
        bar = "▰" * int(conf * 10) + "▱" * (10 - int(conf * 10))
        lines.append(f"Confiança posterior: `{bar}` **{conf:.0%}**")
    return "\n".join(lines)


def _format_dossier(dossier: dict) -> str:
    conf = dossier["confidence"]

    # Convicção na direção do veredito (não probabilidade bruta de aprovação).
    is_against = conf <= 0.34
    is_pro     = conf >= 0.66
    conv = 1 - conf if is_against else conf

    # Rótulo qualitativo — essencial para o leigo entender o número.
    if conv >= 0.85:
        conv_qual = "altíssima convicção"
    elif conv >= 0.70:
        conv_qual = "alta convicção"
    elif conv >= 0.55:
        conv_qual = "convicção moderada"
    else:
        conv_qual = "baixa convicção — área de incerteza"

    if is_against:
        conv_dir = "contra a proposta"
    elif is_pro:
        conv_dir = "a favor da proposta"
    else:
        conv_dir = "sem consenso claro"

    # Header de riscos varia por veredito — linguagem simples, sem jargão.
    if is_against:
        risks_header = "⚠️ **Por que o conselho rejeita:**"
    elif is_pro:
        risks_header = "✅ **Por que o conselho aprova:**"
    else:
        risks_header = "⚖️ **Pontos em aberto:**"

    # Limpa linguagem de debate interno antes de exibir.
    raw_risks = dossier.get("surviving_risks", [])[:4]
    cleaned = [_strip_meta(r) for r in raw_risks]
    risks_block = "\n".join(f"• {r}" for r in cleaned) or "—"

    # Extrai só o veredito (antes do ponto final), sem percentual inline.
    verdict = dossier["recommendation"].split(".")[0].strip()

    return (
        f"🏛️ **VEREDICTO: {verdict}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Convicção do conselho: **{conv:.0%}** {conv_dir}\n"
        f"_(nível de certeza: {conv_qual})_\n\n"
        f"{risks_header}\n{risks_block}\n\n"
        f"_👍 concorda com o conselho · 👎 discorda_"
    )


@tree.command(name="debate", description="Convoca o Conselho AURA para uma decisão.")
@app_commands.describe(
    question="Pergunta estratégica",
    context="Contexto adicional (dados, premissas, restrições)",
    rounds="Número de rodadas adversariais (2-5)",
)
async def debate(
    interaction: discord.Interaction, question: str, rounds: int = 3, context: str = ""
) -> None:
    if rounds < 2 or rounds > 5:
        await interaction.response.send_message(
            "Rounds deve ser entre 2 e 5.", ephemeral=True
        )
        return
    await interaction.response.defer(thinking=True)

    message = await interaction.followup.send(
        _format_progress(0, 0, None), wait=True
    )

    body = {
        "question": question,
        "context": context or None,
        "max_rounds": rounds,
        "mode": os.environ.get("AURA_MODE", "free"),
    }

    claims = 0
    survived = 0
    confidence: float | None = None
    final_dossier: dict | None = None

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as http, http.stream(
            "POST",
            f"{API_BASE}/debates",
            json=body,
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            event_name = "message"
            async for raw in response.aiter_lines():
                if not raw:
                    continue
                if raw.startswith("event:"):
                    event_name = raw.split(":", 1)[1].strip()
                elif raw.startswith("data:"):
                    payload = json.loads(raw.split(":", 1)[1].strip())
                    if event_name == "claim.emitted":
                        claims += 1
                    elif event_name == "score.emitted":
                        if payload.get("payload", {}).get("survived"):
                            survived += 1
                    elif event_name == "dossier":
                        final_dossier = payload
                        confidence = payload["confidence"]

                    # Edit in-place so we don't spam the channel.
                    # Update only after round.finished — at this point all
                    # score.emitted events for the round have been processed,
                    # so both claims and survived counts are accurate.
                    if final_dossier is None and event_name == "round.finished":
                        await message.edit(
                            content=_format_progress(claims, survived, confidence)
                        )
    except Exception as exc:  # network / API failure
        await message.edit(content=f"⚠️ Erro ao chamar AURA: `{exc}`")
        return

    if final_dossier is None:
        await message.edit(content="⚠️ Debate encerrou sem dossier.")
        return

    await message.edit(content=_format_dossier(final_dossier))
    await message.add_reaction("👍")
    await message.add_reaction("👎")


@client.event
async def on_ready() -> None:
    # Sync to the specific guild for instant propagation (vs. up to 1h for global sync)
    guild_id = os.environ.get("DISCORD_GUILD_ID")
    if guild_id:
        guild = discord.Object(id=int(guild_id))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print(f"Commands synced to guild {guild_id}")
    else:
        await tree.sync()
        print("Commands synced globally")
    print(f"AURA Council Bot online as {client.user}")


def main() -> None:
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN not set")
    client.run(TOKEN)


if __name__ == "__main__":
    main()
