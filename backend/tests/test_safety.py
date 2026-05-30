from __future__ import annotations

from aura.safety import redact


def test_redacts_email() -> None:
    out = redact("contato: alguem@example.com hoje")
    assert "alguem@example.com" not in out
    assert "[REDACTED_EMAIL]" in out


def test_redacts_cpf() -> None:
    out = redact("CPF 123.456.789-00 do cliente")
    assert "123.456.789-00" not in out
    assert "[REDACTED_CPF]" in out


def test_passes_through_clean_text() -> None:
    assert redact("texto limpo sem PII") == "texto limpo sem PII"
