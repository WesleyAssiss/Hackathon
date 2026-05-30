# Modelo de Ameaça — AURA

## Premissas
- Nenhum dado real, proprietário ou confidencial entra no sistema (Aviso Legal
  da Liga dos Agentes).
- Datasets são 100 % sintéticos ou de domínio público.

## Vetores cobertos

| Vetor | Mitigação | Camada |
|---|---|---|
| Prompt injection direto (usuário) | Azure AI Content Safety **Prompt Shields** no Gateway | API Gateway |
| Indirect injection via Knowledge Source | Prompt Shields também aplicado ao conteúdo retornado pelo Foundry IQ antes de chegar ao LLM | LLM Client |
| Vazamento de PII | Presidio + regex como segunda camada antes de qualquer LLM call | Safety |
| Claim sem evidência (ungrounded) | Referee rejeita claims sem `Citation` válida; groundedness gate | Referee |
| Segredos em código | Managed Identity + Key Vault; `gitleaks` no CI | DevEx |
| Abuso de API | Rate limit por IP/usuário no Gateway | API Gateway |
| Saída tóxica | Content Safety na resposta antes do streaming SSE | API |

## Suíte de Red-Team (D6)
- 50 prompts conhecidos (DAN, jailbreaks, indirect via KS poisoning) executados
  em CI; métricas publicadas no README.

## Como reportar
Issues de segurança devem ser abertos **privadamente** via GitHub Security
Advisories. Não abra issue público.
