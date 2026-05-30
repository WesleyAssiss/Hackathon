"""PII redaction stub.

D1: regex-only redactor. D2: replace with Microsoft Presidio.
The contract is intentionally minimal so swapping implementations is a
one-line change in the dependency wiring.
"""

from __future__ import annotations

import re
from typing import Final

_EMAIL_RE: Final = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE: Final = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?\(?\d{2,3}\)?[\s-]?\d{3,4}[\s-]?\d{4}\b")
_CPF_RE: Final = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_SSN_RE: Final = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def redact(text: str) -> str:
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = _CPF_RE.sub("[REDACTED_CPF]", text)
    text = _SSN_RE.sub("[REDACTED_SSN]", text)
    return text
