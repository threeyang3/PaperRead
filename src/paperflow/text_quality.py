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


def title_aliases(record: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for value in (
        str(record.get("paper_title") or ""),
        str(record.get("paper_title_display") or ""),
        str(record.get("paper_arxiv_id") or ""),
    ):
        if value and value not in aliases:
            aliases.append(value)
    return aliases
