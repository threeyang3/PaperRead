from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class ReanchorResult:
    status: str
    method: str
    confidence: float
    start: int | None = None
    end: int | None = None


def reanchor_quote(old_text: str, new_text: str, exact: str, *, prefix: str = "",
                   suffix: str = "", threshold: float = 0.86) -> ReanchorResult:
    if not exact:
        return ReanchorResult("page-only", "page", 0.5)
    position = new_text.find(exact)
    if position >= 0:
        if old_text == new_text:
            return ReanchorResult("exact-selection-match", "exact-selection", 1.0,
                                  position, position + len(exact))
        return ReanchorResult("exact-text-match", "exact-text", 1.0,
                              position, position + len(exact))
    contextual = prefix + exact + suffix
    if contextual and contextual in new_text:
        position = new_text.index(contextual) + len(prefix)
        return ReanchorResult("quote-reanchored", "prefix-suffix", 0.98,
                              position, position + len(exact))
    if len(new_text) >= len(exact):
        score, position = max(
            ((SequenceMatcher(None, exact, new_text[i:i + len(exact)]).ratio(), i)
             for i in range(len(new_text) - len(exact) + 1)),
            default=(0.0, 0),
        )
        if score >= threshold:
            return ReanchorResult("quote-reanchored", "fuzzy", round(score, 4),
                                  position, position + len(exact))
    return ReanchorResult("manual-review", "unresolved", 0.0)
