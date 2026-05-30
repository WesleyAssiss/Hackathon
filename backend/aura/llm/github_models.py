"""GitHub Models adapter — 100% gratuito.

GitHub Models (https://github.com/marketplace?type=models) expõe modelos de
fronteira (GPT-4o, Llama, Phi, Mistral, etc.) atrás de um endpoint compatível
com a API da OpenAI. A autenticação usa um **GitHub Personal Access Token**
(PAT) clássico ou um token de Codespaces / Actions — qualquer um já cumpre.

Limites de rate (geração 2025-2026, plano grátis):
    * Free: ~150 requests/dia para GPT-4o-mini, ~50/dia para GPT-4o.
    * Para uma demo de hackathon (~30 requests) sobra MUITO.

Use este client quando você quer rodar AURA com inteligência real **sem
gastar 1 centavo**. É a opção padrão do modo "free".
"""

from __future__ import annotations

import os
from typing import ClassVar

from aura.llm.client import BaseLLMClient, LLMResponse


class GitHubModelsClient(BaseLLMClient):
    """Async wrapper sobre `openai.AsyncOpenAI` apontando para o GitHub Models.

    Variáveis:
        GITHUB_TOKEN     — PAT (qualquer escopo serve, sem 'repo' é suficiente).
        AURA_GH_MODEL    — nome do modelo (default: ``gpt-4o-mini``).
        AURA_GH_ENDPOINT — endpoint (default: ``https://models.inference.ai.azure.com``).
    """

    # Ordem de preferência quando o usuário pede "auto". Modelos confirmados
    # disponíveis no endpoint `models.inference.ai.azure.com` primeiro. Modelo
    # que toma 429 fica em cooldown de 60s; que toma 400/404 fica em cooldown
    # de 600s (provavelmente nome inválido para este endpoint).
    _AUTO_CHAIN = (
        "Llama-3.2-11B-Vision-Instruct",
        "Mistral-small",
        "Phi-3.5-MoE-instruct",
        "Phi-3-medium-128k-instruct",
        "gpt-4o-mini",
        "gpt-4o",
    )
    # Backoff por modelo (epoch em que volta a estar disponível). Compartilhado
    # entre instâncias do client para que clientes recém-criados respeitem o
    # backoff já observado.
    _cooldown: ClassVar[dict[str, float]] = {}

    def __init__(
        self,
        *,
        token: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        token = token or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN não configurado. Crie um PAT em "
                "https://github.com/settings/tokens (qualquer escopo serve) "
                "e exporte como GITHUB_TOKEN."
            )

        from openai import AsyncOpenAI  # type: ignore[import-not-found]

        requested = model or os.environ.get("AURA_GH_MODEL", "gpt-4o-mini")
        self._auto = requested.strip().lower() == "auto"
        self._model = self._AUTO_CHAIN[0] if self._auto else requested
        # Telemetria observada pelo Orchestrator (calls realmente atingiram a
        # rede; 429/400/timeouts contam separadamente).
        self._call_count = 0
        self._error_count = 0
        self._client = AsyncOpenAI(
            api_key=token,
            base_url=endpoint
            or os.environ.get(
                "AURA_GH_ENDPOINT", "https://models.inference.ai.azure.com"
            ),
        )

    @property
    def call_stats(self) -> dict[str, int]:
        return {"calls": self._call_count, "errors": self._error_count}

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 512
    ) -> LLMResponse:
        import asyncio
        import time

        # Cadeia a tentar: em modo auto, percorre _AUTO_CHAIN pulando os que
        # estão em cooldown. Caso contrário, só o modelo fixo.
        if self._auto:
            now = time.monotonic()
            chain = [m for m in self._AUTO_CHAIN if self._cooldown.get(m, 0.0) <= now]
            if not chain:
                # Todos em cooldown — tenta o mais cedo a liberar
                chain = [min(self._AUTO_CHAIN, key=lambda m: self._cooldown.get(m, 0.0))]
        else:
            chain = [self._model]

        backoffs = (2.0, 5.0, 9.0)
        last_exc: Exception | None = None
        response = None
        used_model = chain[0]

        for model_name in chain:
            used_model = model_name
            response = None
            for attempt, delay in enumerate(backoffs):
                try:
                    response = await self._client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        max_tokens=max_tokens,
                        temperature=0.3,
                        top_p=0.9,
                    )
                    self._call_count += 1
                    last_exc = None
                    break
                except Exception as exc:
                    self._error_count += 1
                    last_exc = exc
                    err = str(exc).lower()
                    # 400/404 = modelo inválido/indisponível neste endpoint.
                    # Não adianta retry — quebra imediatamente para pular
                    # para o próximo modelo da chain (em modo auto).
                    if "400" in err or "404" in err or "not found" in err or "unknown model" in err:
                        break
                    retryable = "rate" in err or "429" in err
                    if retryable and attempt < len(backoffs) - 1:
                        await asyncio.sleep(delay)
                        continue
                    break
            if response is not None:
                break
            # Esse modelo falhou; em auto, marca cooldown e tenta o próximo.
            if self._auto and last_exc is not None:
                err = str(last_exc).lower()
                if "400" in err or "404" in err or "not found" in err or "unknown model" in err:
                    # Modelo desconhecido para o endpoint → cooldown longo (10 min).
                    self._cooldown[model_name] = time.monotonic() + 600.0
                elif "rate" in err or "429" in err:
                    self._cooldown[model_name] = time.monotonic() + 60.0

        if response is None:
            err = str(last_exc).lower() if last_exc else ""
            if "content_filter" in err or "responsibleai" in err or "jailbreak" in err:
                reason = "filtro de conteúdo do provedor"
            elif "rate" in err or "429" in err:
                reason = "rate-limit do provedor"
            else:
                reason = "erro transitório do provedor"
            return LLMResponse(
                text=f"[Sem resposta nesta rodada — {reason}.]",
                confidence=0.15,
            )

        # Em auto, atualiza o "último que funcionou" para priorizar nas próximas
        if self._auto:
            self._model = used_model

        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        if not text:
            return LLMResponse(
                text="[Resposta vazia do provedor — sem evidência adicional.]",
                confidence=0.15,
            )
        confidence = 0.7 if choice.finish_reason == "stop" else 0.5
        return LLMResponse(text=text, confidence=confidence)
