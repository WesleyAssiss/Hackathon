# Provenance de Dados — AURA

> **Política:** zero dados reais, proprietários ou confidenciais. Todos os
> datasets utilizados são **sintéticos** (gerados por script determinístico) ou
> de **domínio público**.

## Datasets planejados (D2)

| Dataset | Origem | Licença | Uso |
|---|---|---|---|
| `synthetic_market_reports.jsonl` | Gerado por `scripts/gen_market_data.py` | MIT (este repo) | Knowledge Source do CFO Agent |
| `synthetic_company_tech_stacks.jsonl` | Gerado por script | MIT | Knowledge Source do CTO Agent |
| `nvd_cve_subset.jsonl` | NIST NVD (público) | US Gov Public Domain | Knowledge Source do Red-Team Agent |
| `synthetic_g2_reviews.jsonl` | Gerado por script | MIT | Knowledge Source do Customer Agent |
| `hbr_failure_patterns_summary.md` | Resumos próprios de leituras públicas | CC-BY (atribuição) | Knowledge Source do Historian Agent |

## Geração
Scripts em `scripts/` são determinísticos (seed fixo) e incluem cabeçalho com
data, seed e hash dos artefatos gerados para auditoria.

## Verificação
Antes de cada submissão:
```bash
python scripts/verify_no_secrets.py
gitleaks detect --no-git
```
