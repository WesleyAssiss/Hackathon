# Credenciais — guia 100% grátis

> **Resposta direta à sua pergunta**: SIM, dá para apresentar AURA com
> inteligência de fronteira (GPT-4o, Llama 70B, Mistral Large) **sem gastar 1
> centavo, sem cartão de crédito, sem crédito Azure que expira**. O caminho
> abaixo cobre tudo.

---

## 🆓 Stack 100% gratuita (modo `free`)

| Componente            | Onde pegar                                                          | Custo |
|-----------------------|---------------------------------------------------------------------|-------|
| **GitHub Models**     | https://github.com/marketplace?type=models (precisa só de um PAT)   | **R$ 0** |
| **GitHub PAT**        | https://github.com/settings/tokens → "Generate new token (classic)" | **R$ 0** |
| **Discord Bot Token** | https://discord.com/developers/applications → New Application → Bot | **R$ 0** |
| **GitHub Copilot**    | Já tem se você está num plano free para estudantes / OSS / Liga     | **R$ 0** |
| **Hosting local**     | seu próprio laptop (uvicorn) — basta abrir o navegador              | **R$ 0** |

**Total: R$ 0 / US$ 0. Sem cartão. Sem deadline de crédito. Funciona offline em modo mock.**

---

## 1. GitHub Models — o coração grátis

GitHub Models é a vitrine free da Microsoft com **GPT-4o, GPT-4o-mini,
Llama 3.3 70B, Mistral Large, Phi-3.5 MoE, DeepSeek**, entre outros. Compatível
com o SDK da OpenAI, então plugou e usou.

### 1.1. Criar o Personal Access Token

1. Abra **https://github.com/settings/tokens**
2. Clique em **"Generate new token (classic)"**
3. **Note**: `AURA Hackathon`
4. **Expiration**: 30 dias (ou o que preferir)
5. **Scopes**: **NÃO precisa marcar nenhum** — Models aceita PAT "vazio".
6. Clique em **Generate token** no rodapé.
7. Copie o token (começa com `ghp_…`) e cole em `GITHUB_TOKEN=` no seu `.env`.

### 1.2. Limites de rate (free tier — gen. 2025-2026)

| Modelo            | Requests/dia | Tokens/request |
|-------------------|--------------|----------------|
| gpt-4o-mini       | 150          | 4.000          |
| gpt-4o            | 50           | 8.000          |
| Llama-3.3-70B     | 150          | 8.000          |
| Mistral-large     | 50           | 8.000          |
| text-embedding-3  | 150          | —              |

Um debate AURA usa **~7-12 requests** (5 personas × 1-2 turnos + Referee). Você
roda **15-20 demos por dia** tranquilo. **Mais que suficiente** para hackathon.

---

## 2. Discord Bot — 100% grátis

1. https://discord.com/developers/applications → **"New Application"** → nome
   `AURA Council`.
2. Menu lateral: **Bot** → **Reset Token** → copie → cole em
   `DISCORD_BOT_TOKEN=` no `.env`.
3. **OAuth2 → URL Generator**:
   - Escopos: `bot`, `applications.commands`
   - Permissões: `Send Messages`, `Embed Links`, `Add Reactions`,
     `Use Slash Commands`
4. Cole a URL gerada no navegador → escolha um servidor seu de testes → autorize.

Custo: **R$ 0**. Discord não cobra por bots.

---

## 3. Hosting do app — 100% grátis no seu laptop

Para a apresentação, **rode local**. Não precisa cloud para um pitch de 3 min.

```powershell
# Terminal 1 — sobe a API com a War Room
.\.venv\Scripts\python -m uvicorn aura.api.main:app --port 8000

# Abra o navegador
start http://localhost:8000
```

Quer streamar pro mundo durante a demo (caso a apresentação seja remota)?
Use um **tunnel grátis**:

```powershell
# Tunnel Cloudflare — sem cadastro, sem cartão
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8000
```

Ou **ngrok free** (https://ngrok.com — 1 tunnel grátis para sempre).

Custo: **R$ 0**.

---

## 4. Quando faz sentido subir o Azure?

Honestamente: **só se você quiser pontuar mais alto em "Foundry IQ pesado"** ou
ganhar bônus pela trilha. Para a entrega do hackathon, **modo `free` cumpre
100% do regulamento** porque:

- Foundry IQ na nova definição da Microsoft inclui a família **Foundry Models**
  → **GitHub Models é Foundry**.
- O critério é "integração com Microsoft IQ", não "consumo pago de Azure".

Se mesmo assim quiser, o `azd up` cria tudo no tier mais barato (Search Free
SKU + Container Apps free + Log Analytics free). O único pago é o **AOAI**, e
mesmo ele cabe nos US$ 200 de crédito free de uma conta nova.

> Para zerar o risco de cobrança: **defina um Budget de US$ 5 com alerta em
> 80%** em Cost Management. Você é avisado por e-mail antes de qualquer susto.

---

## 5. Checklist de 90 segundos para começar a usar

```powershell
# 1. Clone o repo (você já tem)
cd C:\Users\Wesley\Documents\Hackathon

# 2. Crie e edite o .env
Copy-Item .env.example .env
notepad .env
#   → cole seu GITHUB_TOKEN
#   → confirme AURA_MODE=free

# 3. Instale a dependência mínima do free mode
.\.venv\Scripts\pip install -e ".[dev]" openai

# 4. Rode os testes (deve dar 71 passed)
.\.venv\Scripts\python -m pytest -q

# 5. Sobe a API
.\.venv\Scripts\python -m uvicorn aura.api.main:app --port 8000

# 6. Abre a War Room
start http://localhost:8000
```

Pronto. Você tem AURA com **inteligência real (GPT-4o, Llama 70B)** rodando
**de graça**.
