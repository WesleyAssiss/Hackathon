"""Prompt-injection detector.

A pragmatic, deterministic first line of defense — runs *before* any LLM
call and *after* every Knowledge Source fetch (indirect injection).
Azure AI Content Safety Prompt Shields will sit in front of this in D2; the
two layers compose (defense in depth).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# Patterns are intentionally conservative — high precision over recall to
# avoid false-positive denials during the demo. The Red-Team test suite
# (`backend/tests/test_injection_suite.py`) gates regression.
_IGNORE_NOUN = r"(instruct|instru\xe7|prompt|rule|regra)"
_IGNORE_VERB = r"(ignor[ae]|disregard|forget|esque[cs]a|override)"
_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    # "ignore / disregard / override ... instruct/prompt/rules" with up
    # to ~60 chars between the verb and the target noun. EN + PT.
    (
        "ignore_previous",
        re.compile(rf"\b{_IGNORE_VERB}\b.{{0,60}}?{_IGNORE_NOUN}", re.I | re.S),
    ),
    (
        "system_override",
        re.compile(
            r"\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be|aja\s+como|system\s+override)\b",
            re.I,
        ),
    ),
    (
        "role_break",
        re.compile(r"\bsystem\s*[:>]|\bassistant\s*[:>]|<\|im_start\|>", re.I),
    ),
    (
        "dan_jailbreak",
        re.compile(
            r"\b(DAN|do\s+anything\s+now|developer\s+mode|jailbreak)\b", re.I
        ),
    ),
    # "print/reveal/leak/dump/show/output/translate/repeat ... prompt|instructions"
    (
        "data_exfil",
        re.compile(
            r"\b(print|reveal|leak|dump|show|output|translate|repeat|disclose)\b"
            r".{0,60}?\b(prompt|instruction|configur)",
            re.I | re.S,
        ),
    ),
    # "hidden ... prompt|instructions" — covers "hidden instructions",
    # "hidden system prompt" etc. regardless of the verb.
    (
        "hidden_directive",
        re.compile(r"\bhidden\b.{0,40}?\b(prompt|instruction|directive)", re.I | re.S),
    ),
    ("encoded_payload", re.compile(r"base64|data:text/", re.I)),
    (
        "html_comment_directive",
        re.compile(r"<!--.*?(system|ignore|prompt).*?-->", re.I | re.S),
    ),
)


@dataclass(frozen=True, slots=True)
class InjectionVerdict:
    blocked: bool
    matched_rules: tuple[str, ...]

    @property
    def reason(self) -> str:
        if not self.blocked:
            return "clean"
        return "matched: " + ", ".join(self.matched_rules)


def detect(text: str) -> InjectionVerdict:
    hits = tuple(name for name, pat in _PATTERNS if pat.search(text))
    return InjectionVerdict(blocked=bool(hits), matched_rules=hits)


class InjectionBlocked(Exception):
    def __init__(self, verdict: InjectionVerdict) -> None:
        super().__init__(verdict.reason)
        self.verdict = verdict


def guard(text: str) -> str:
    """Raise `InjectionBlocked` if `text` looks like a prompt-injection attack."""
    verdict = detect(text)
    if verdict.blocked:
        raise InjectionBlocked(verdict)
    return text
