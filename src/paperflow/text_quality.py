from __future__ import annotations

import re
import unicodedata
from typing import Any


MOJIBAKE_MARKERS = (
    "鏈",
    "锛",
    "銆",
    "鈥",
    "蟺",
    "�",
)
_SUSPICIOUS_RE = re.compile("|".join(re.escape(item) for item in MOJIBAKE_MARKERS))
_LATEX_GREEK = {
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ε",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\pi": "π",
    r"\rho": "ρ",
    r"\sigma": "σ",
    r"\tau": "τ",
    r"\phi": "φ",
    r"\psi": "ψ",
    r"\omega": "ω",
}
_SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_SUPERSCRIPT = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")


def suspicious_text(value: str) -> bool:
    """Return True for replacement characters and common UTF-8/GBK mojibake."""
    return bool(_SUSPICIOUS_RE.search(value))


def validate_text_quality(value: Any, *, label: str = "text") -> None:
    """Reject corrupted strings recursively before immutable persistence."""
    if isinstance(value, str):
        if suspicious_text(value):
            raise ValueError(f"{label} contains probable mojibake")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            validate_text_quality(child, label=f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            validate_text_quality(child, label=f"{label}[{index}]")


def display_title(source_title: str) -> str:
    """Create a readable Obsidian title without translating the source."""
    value = unicodedata.normalize("NFC", " ".join(source_title.split()))
    for latex, symbol in _LATEX_GREEK.items():
        value = value.replace(latex, symbol)
    value = re.sub(
        r"_\{([0-9+\-=().]+)\}",
        lambda match: match.group(1).translate(_SUBSCRIPT),
        value,
    )
    value = re.sub(
        r"\^\{([0-9+\-=().]+)\}",
        lambda match: match.group(1).translate(_SUPERSCRIPT),
        value,
    )
    value = value.replace(r"\ ", " ")
    value = re.sub(r"\$(.*?)\$", r"\1", value)
    return " ".join(value.split()).strip()


def short_title(source_title: str, *, max_length: int = 72) -> str:
    """Return a deterministic, human-friendly title fragment.

    This is deliberately derived from the source title and never replaces it.
    A subtitle after a colon/em dash is omitted when the leading fragment is
    meaningful; otherwise the display title is safely truncated.
    """
    value = display_title(source_title)
    if not value:
        return "Untitled"
    first = re.split(r"\s*(?::|[\u2013\u2014]|\\ - )\s*", value, maxsplit=1)[0]
    candidate = first.strip() if len(first.strip()) >= 4 else value
    if len(candidate) <= max_length:
        return candidate
    return candidate[: max_length - 1].rstrip(" ,.;:-") + "…"


def user_display_title(record: dict[str, Any]) -> str:
    """Resolve a user title override without allowing Raw/AI to own it."""
    for key in ("user_display_title", "user_title"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return ""


def title_aliases(record: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    paper_id = str(record.get("paper_arxiv_id") or "").strip()
    override = user_display_title(record)
    for value in (
        str(record.get("paper_title") or ""),
        str(record.get("paper_title_display") or ""),
        str(record.get("paper_short_title") or short_title(str(record.get("paper_title") or ""))),
        override,
        paper_id,
        f"arXiv {paper_id}" if paper_id else "",
    ):
        if value and value not in aliases:
            aliases.append(value)
    # Preserve aliases authored in Obsidian while deduplicating deterministically.
    for value in record.get("aliases", []) or []:
        value = str(value).strip()
        if value and value not in aliases:
            aliases.append(value)
    return aliases
