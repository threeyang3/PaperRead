"""Bounded text extraction for provider prompts.

Preserve the beginning and end even when a paper has no English section
headings (e.g. Chinese OCR, scanned text, or an atypical layout).
"""
from __future__ import annotations

import re

TARGETS = [
    "abstract", "introduction", "related work", "method", "approach",
    "experiment", "result", "conclusion", "limitation",
]


def select_context(text: str, limit: int = 160_000) -> str:
    if limit < 1:
        raise ValueError("context limit must be positive")
    if len(text) <= limit:
        return text
    if limit < 1024:
        return text[:limit]
    # The introductory section and conclusion must never disappear, including
    # for documents without headings/URLs. The remainder targets key sections.
    intro_budget = min(12_000, max(256, limit // 5))
    ending_budget = min(8_000, max(256, limit // 8))
    section_budget = limit - intro_budget - ending_budget
    excerpt_length = max(512, section_budget // (len(TARGETS) + 2))
    lowered = text.lower()
    chunks: list[str] = [text[:intro_budget]]
    for target in TARGETS:
        matches = re.finditer(
            rf"(?m)^.*\b{re.escape(target)}s?\b.*$", lowered
        )
        for idx, match in enumerate(matches):
            if idx >= 2:
                break
            start = max(0, match.start() - 500)
            chunks.append(text[start:start + excerpt_length])
    for idx, match in enumerate(re.finditer(r"https?://\S+", text)):
        if idx >= 10:
            break
        chunks.append(text[max(0, match.start() - 250):match.end() + 250])
    tail = text[-ending_budget:]
    unique = list(dict.fromkeys(chunks))
    selected = "\n\n[SELECTED SECTION]\n".join(unique)
    # Explicitly reserve the tail: earlier long sections must not consume it.
    prefix_budget = max(0, limit - len(tail) - len("\n\n[DOCUMENT END]\n"))
    return selected[:prefix_budget] + "\n\n[DOCUMENT END]\n" + tail
