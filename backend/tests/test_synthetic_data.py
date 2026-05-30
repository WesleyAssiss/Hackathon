from __future__ import annotations

from pathlib import Path

from scripts.gen_synthetic_data import generate, write


def test_generation_is_deterministic() -> None:
    first = generate()
    second = generate()
    assert {k: [r.text_sha256 for r in v] for k, v in first.items()} == {
        k: [r.text_sha256 for r in v] for k, v in second.items()
    }


def test_write_emits_jsonl(tmp_path: Path) -> None:
    counts = write(tmp_path)
    assert set(counts) == {"cfo", "cto", "customer", "red_team", "historian"}
    for persona in counts:
        path = tmp_path / f"{persona}.jsonl"
        assert path.exists()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == counts[persona]
        # JSON-parseable, sorted by chunk_id
        import json as _json

        records = [_json.loads(line) for line in lines]
        ids = [r["chunk_id"] for r in records]
        assert ids == sorted(ids)
