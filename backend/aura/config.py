"""Configuration loaded from environment with safe defaults.

Centralized so every adapter pulls from the same place — secrets only ever
come from env / Key Vault, never from code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Carrega .env do repo root (sobe até 4 níveis até achar um).
    _here = Path(__file__).resolve()
    for _candidate in [_here.parent, *_here.parents]:
        _env_path = _candidate / ".env"
        if _env_path.is_file():
            load_dotenv(_env_path, override=False)
            break
except ImportError:  # python-dotenv é opcional em runtime de produção (MI cuida)
    pass


def _get(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name, default)
    return val.strip() if isinstance(val, str) and val.strip() else default


@dataclass(frozen=True, slots=True)
class AzureSettings:
    aoai_endpoint: str | None
    aoai_deployment: str
    aoai_api_version: str
    foundry_project_endpoint: str | None
    foundry_knowledge_index: str
    use_managed_identity: bool

    @property
    def aoai_configured(self) -> bool:
        return bool(self.aoai_endpoint)

    @property
    def foundry_configured(self) -> bool:
        return bool(self.foundry_project_endpoint)


def load_azure_settings() -> AzureSettings:
    return AzureSettings(
        aoai_endpoint=_get("AURA_AOAI_ENDPOINT"),
        aoai_deployment=_get("AURA_AOAI_DEPLOYMENT", "gpt-4.1") or "gpt-4.1",
        aoai_api_version=_get("AURA_AOAI_API_VERSION", "2024-10-21") or "2024-10-21",
        foundry_project_endpoint=_get("AURA_FOUNDRY_PROJECT_ENDPOINT"),
        foundry_knowledge_index=_get("AURA_FOUNDRY_KNOWLEDGE_INDEX", "aura-corpus")
        or "aura-corpus",
        use_managed_identity=(_get("AURA_USE_MANAGED_IDENTITY", "true") or "true").lower()
        == "true",
    )
