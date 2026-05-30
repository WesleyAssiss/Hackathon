"""Ingest the synthetic corpus into Azure AI Search (the storage layer used
by Foundry IQ Knowledge Sources).

Usage:
    az login
    $env:AURA_AOAI_ENDPOINT       = "https://<aoai>.openai.azure.com"
    $env:AURA_FOUNDRY_PROJECT_ENDPOINT = "https://<search>.search.windows.net"
    $env:AURA_FOUNDRY_KNOWLEDGE_INDEX  = "aura-corpus"
    python scripts/ingest_to_foundry.py --data data/synthetic --create-index

Safe to re-run: the index is upserted, never deleted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
sys.path.insert(0, str(_REPO / "backend"))

from aura.config import load_azure_settings  # noqa: E402
from aura.observability import configure_logging, get_logger  # noqa: E402

_log = get_logger("aura.ingest")


def _records(data_dir: Path):
    for jsonl in sorted(data_dir.glob("*.jsonl")):
        persona = jsonl.stem
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            yield {
                "id": f"{persona}-{r['chunk_id']}",
                "persona": persona,
                "chunk_id": r["chunk_id"],
                "knowledge_source_id": r.get("knowledge_source_id", f"synthetic_{persona}"),
                "text": r["text"],
            }


async def _ensure_index(endpoint: str, index_name: str, credential) -> None:
    from azure.search.documents.indexes.aio import SearchIndexClient
    from azure.search.documents.indexes.models import (
        SearchableField,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SimpleField,
    )

    idx_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    try:
        fields: list[SearchField] = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
            SimpleField(name="persona", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="chunk_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(
                name="knowledge_source_id",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchableField(
                name="text",
                type=SearchFieldDataType.String,
                analyzer_name="standard.lucene",
            ),
        ]
        index = SearchIndex(name=index_name, fields=fields)
        await idx_client.create_or_update_index(index)
        _log.info("aura.ingest.index_ready", index=index_name)
    finally:
        await idx_client.close()


async def _upload(endpoint: str, index_name: str, docs: list[dict], credential) -> None:
    from azure.search.documents.aio import SearchClient

    client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)
    try:
        result = await client.upload_documents(documents=docs)
        ok = sum(1 for r in result if r.succeeded)
        _log.info("aura.ingest.uploaded", total=len(docs), ok=ok)
    finally:
        await client.close()


async def main_async(data_dir: Path, create_index: bool) -> int:
    configure_logging()
    settings = load_azure_settings()
    if not settings.foundry_configured:
        _log.error("aura.ingest.missing_endpoint")
        return 2

    from azure.identity.aio import (
        AzureCliCredential,
        ChainedTokenCredential,
        DefaultAzureCredential,
    )

    credential = (
        ChainedTokenCredential(DefaultAzureCredential(), AzureCliCredential())
        if settings.use_managed_identity
        else AzureCliCredential()
    )
    try:
        endpoint = settings.foundry_project_endpoint  # type: ignore[assignment]
        index_name = settings.foundry_knowledge_index

        if create_index:
            await _ensure_index(endpoint, index_name, credential)

        docs = list(_records(data_dir))
        if not docs:
            _log.error("aura.ingest.no_records", data_dir=str(data_dir))
            return 3
        await _upload(endpoint, index_name, docs, credential)
        return 0
    finally:
        await credential.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--create-index", action="store_true")
    args = parser.parse_args()
    return asyncio.run(main_async(args.data, args.create_index))


if __name__ == "__main__":
    raise SystemExit(main())
