from __future__ import annotations

import re
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"(?i)(?:api[_-]?key|token|password|cookie|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"),
]
PATH_PATTERN = re.compile(
    r"(?i)(?:[A-Z]:[\\/](?:Users[\\/])?|/home/|/Users/|\\\\[^\\]+\\)"
)
MAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
ACTIVE_CONTENT = re.compile(
    r"(?is)<\s*(?:script|iframe|object|embed|style)\b|"
    r"(?:javascript|data|vbscript)\s*:|on\w+\s*="
)
IMAGE_OR_PDF = re.compile(
    r"(?i)!\[\[|!\[[^\]]*\]\(|\[\[[^\]]+\.(?:png|jpe?g|gif|svg|webp|pdf)"
)


def scan_community_contribution(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    text = "\n".join(
        str(value.get(key, "")) for key in ("body", "creator", "supersedes")
    )
    if PATH_PATTERN.search(text):
        findings.append("absolute/local path")
    if MAIL_PATTERN.search(text):
        findings.append("email address")
    if ACTIVE_CONTENT.search(text):
        findings.append("active HTML or unsafe URI scheme")
    if IMAGE_OR_PDF.search(text):
        findings.append("image or PDF embedding")
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        findings.append("credential-like value")
    anchor = value.get("anchor") or {}
    if len(str(anchor.get("exact_quote", ""))) > 500:
        findings.append("quoted passage exceeds 500 characters")
    if len(text.encode("utf-8")) > 64 * 1024:
        findings.append("contribution exceeds 64 KiB")
    if any(key.startswith("user_") for key in value):
        findings.append("private user_* property")
    return sorted(set(findings))
