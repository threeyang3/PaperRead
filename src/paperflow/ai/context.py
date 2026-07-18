from __future__ import annotations
import re

TARGETS = ["abstract", "introduction", "related work", "method", "approach", "experiment", "result", "conclusion", "limitation"]


def select_context(text: str, limit: int = 160_000) -> str:
    if len(text) <= limit:
        return text
    chunks: list[str] = []
    per = max(4000, limit // (len(TARGETS) + 2))
    lowered = text.lower()
    for target in TARGETS:
        for match in list(re.finditer(rf"(?m)^.*\b{re.escape(target)}s?\b.*$", lowered))[:2]:
            start = max(0, match.start() - 500)
            chunks.append(text[start:start + per])
    for match in list(re.finditer(r"https?://\S+", text))[:20]:
        chunks.append(text[max(0, match.start() - 500):match.end() + 500])
    unique = list(dict.fromkeys(chunks))
    return "\n\n[SELECTED SECTION]\n".join(unique)[:limit]

