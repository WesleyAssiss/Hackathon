"""Abstract LLM client + deterministic mock implementation.

The Azure-backed adapter (GPT-4.1 via Foundry Agent Service) lands in D2.
Until then every code path is exercised against `MockLLMClient`, which makes
tests deterministic and cheap.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Protocol


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    confidence: float


class LLMClient(Protocol):
    async def complete(self, *, system: str, user: str, max_tokens: int = 512) -> LLMResponse: ...


class BaseLLMClient(ABC):
    @abstractmethod
    async def complete(
        self, *, system: str, user: str, max_tokens: int = 512
    ) -> LLMResponse: ...


class MockLLMClient(BaseLLMClient):
    """Deterministic mock used in tests and demo `mode=mock`.

    Returns realistic persona-appropriate statements so the demo looks
    convincing without any network call.
    """

    # Persona-keyed statement banks -- varied enough to produce distinct rounds.
    _STMTS: ClassVar[dict[str, list[str]]] = {
        "cfo": [
            "Do ponto de vista financeiro, o payback estimado supera 18 meses sem "
            "validação de receita prévia. Recomendo um piloto limitado antes de "
            "comprometer orçamento completo.",
            "A análise de fluxo de caixa indica risco operacional elevado. "
            "O custo de oportunidade de capital comprometido agora versus um go-live "
            "faseado pode representar diferença de 30-40% no VPL do projeto.",
            "Sem runway confirmado para absorver o burn adicional nos primeiros 2 "
            "trimestres, o risco de liquidez é não desprezível. Exijo um gatilho "
            "de receita antes da fase 2.",
        ],
        "cto": [
            "A arquitetura de microsserviços atual suporta a iniciativa. "
            "O débito técnico acumulado no serviço de autenticação, porém, exige "
            "refatoração prévia — sem isso, o risco de incidente em produção aumenta.",
            "A stack está pronta para escalar horizontalmente. O ponto crítico é a "
            "ausência de testes de carga end-to-end validando o throughput exigido "
            "pelo SLA — recomendo shadow-mode por 2 semanas antes do GA.",
            "Tecnicamente viável no prazo. Porém dependemos de uma lib externa sem "
            "suporte LTS — isso é um risco de manutenção que precisa ser endereçado "
            "antes de entrar em produção.",
        ],
        "customer": [
            "Pesquisas com usuários Beta mostram 73% de preferência pela nova "
            "experiência. O risco de churn na transição está dentro da margem "
            "aceitável (<5%), desde que a comunicação seja proativa.",
            "Clientes enterprise sinalizaram resistência a mudanças abruptas na "
            "jornada. Uma migração gradual com opt-in reduz o atrito e preserva "
            "o NPS na faixa atual.",
            "O feedback qualitativo indica que o diferencial percebido pelo cliente "
            "é alto — porém apenas se a latência permanecer abaixo de 200ms. "
            "Qualquer degradação reverte a percepção positiva.",
        ],
        "red_team": [
            "Identifiquei 3 vetores críticos: (1) dependência de fornecedor único "
            "sem SLA contratual, (2) ausência de plano de rollback documentado, "
            "(3) modelo de IA sem validação em produção — shadow-mode é mandatório.",
            "O pior cenário envolve falha regulatória. O BACEN pode exigir "
            "adequações que atrasem o go-live em até 6 meses e gerem multa "
            "de R$ 2M-10M por violação do normativo de continuidade operacional.",
            "Zero-day na dependência principal foi divulgado há 3 semanas — "
            "o patch ainda não foi aplicado. Avançar em produção com essa "
            "vulnerabilidade aberta é inaceitável do ponto de vista de segurança.",
        ],
        "historian": [
            "Casos análogos (Nubank 2019, PicPay 2020) mostram 65% de taxa de "
            "sucesso quando precedidos de fase piloto com amostra controlada. "
            "Projetos que pularam o piloto tiveram rollback em 40% dos casos.",
            "O histórico do setor indica que o maior risco é subestimar o tempo "
            "de integração: o prazo real foi 2,4x o estimado nas primeiras 3 "
            "implementações similares catalogadas entre 2018-2022.",
            "Iniciativas comparáveis falharam principalmente por falta de "
            "patrocínio executivo sustentado além do quarter inicial. "
            "O comprometimento de longo prazo da liderança é o preditor mais "
            "forte de sucesso nesse tipo de projeto.",
        ],
    }
    _GENERIC = (
        "A análise desta questão requer dados adicionais antes de uma recomendação "
        "definitiva. Os indicadores atuais são inconclusivos para uma decisão de alto impacto."
    )

    def __init__(self, scripted_responses: dict[str, str] | None = None) -> None:
        self._scripted = scripted_responses or {}

    # ------------------------------------------------------------------
    def _persona_slug(self, system: str) -> str:
        sl = system.lower()
        if "cfo" in sl or "financeiro" in sl or "chief financial" in sl:
            return "cfo"
        if "cto" in sl or "tecnologia" in sl or "chief technology" in sl:
            return "cto"
        if "cliente" in sl or "customer" in sl or "voz do cliente" in sl:
            return "customer"
        if "red" in sl and ("team" in sl or "risco" in sl or "analista" in sl):
            return "red_team"
        if "historiador" in sl or "historian" in sl or "casos análogos" in sl:
            return "historian"
        return "generic"

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 512
    ) -> LLMResponse:
        for needle, text in self._scripted.items():
            if needle in system:
                return LLMResponse(text=text, confidence=0.7)

        slug = self._persona_slug(system)
        bank = self._STMTS.get(slug)
        if bank is None:
            return LLMResponse(text=self._GENERIC, confidence=0.5)

        # Deterministic selection: vary by round (encoded in user prompt length)
        idx = (len(user) // 17 + len(system) // 31) % len(bank)
        confidence = 0.55 + 0.05 * (idx % 3)
        return LLMResponse(text=bank[idx], confidence=confidence)
