"""Fail-closed filesystem boundaries for remote and logical identifiers.

The helpers in this module are deliberately stricter than display-name slug
functions.  They are used only for system-managed storage, where accepting a
path-shaped identifier would create an ambiguous or unsafe write target.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Iterable


_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{value}" for value in range(1, 10)),
    *(f"LPT{value}" for value in range(1, 10)),
}
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_SAFE_ASCII = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")


class PathSecurityError(ValueError):
    """Raised when an identifier or path crosses a managed boundary."""


def safe_storage_component(
    value: object,
    *,
    label: str,
    max_length: int = 100,
) -> str:
    """Return one deterministic filesystem component or reject the input.

    Logical punctuation (for example the colon in an arXiv UID) is encoded,
    rather than stripped, so distinct valid identifiers do not collapse under
    ordinary slug rules.  Path syntax is rejected before encoding.
    """

    if max_length < 24:
        raise ValueError("max_length must be at least 24")
    raw = "" if value is None else str(value)
    normalized = unicodedata.normalize("NFKC", raw)
    if not normalized or normalized != normalized.strip():
        raise PathSecurityError(f"invalid {label}")
    if "\x00" in normalized or normalized in {".", ".."}:
        raise PathSecurityError(f"invalid {label}")
    if "/" in normalized or "\\" in normalized:
        raise PathSecurityError(f"path syntax is forbidden in {label}")
    if normalized.startswith(("/", "\\")) or _DRIVE_PATH.match(normalized):
        raise PathSecurityError(f"absolute path syntax is forbidden in {label}")
    stem = normalized.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise PathSecurityError(f"reserved storage name is forbidden in {label}")

    # Preserve the established ``arxiv_2607.00001`` schema-3 layout. A
    # collection boundary must still reject a literal-underscore collision.
    encoded = "".join(
        "_"
        if character == ":"
        else character
        if character in _SAFE_ASCII
        else "".join(f"~{byte:02X}" for byte in character.encode("utf-8"))
        for character in normalized
    )
    encoded = encoded.rstrip(" .")
    if not encoded or encoded in {".", ".."}:
        raise PathSecurityError(f"invalid {label}")
    if len(encoded) > max_length:
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        prefix_length = max_length - len(digest) - 2
        encoded = f"{encoded[:prefix_length].rstrip(' .-')}~h{digest}"
    if not encoded or "/" in encoded or "\\" in encoded:
        raise PathSecurityError(f"invalid {label}")
    return encoded


def assert_distinct_storage_components(
    values: Iterable[object],
    *,
    label: str,
    max_length: int = 100,
) -> dict[str, str]:
    """Encode identifiers while rejecting normalization or truncation clashes."""

    encoded: dict[str, str] = {}
    originals: dict[str, str] = {}
    for value in values:
        raw = "" if value is None else str(value)
        component = safe_storage_component(value, label=label, max_length=max_length)
        key = component.casefold()
        previous = originals.get(key)
        if previous is not None and previous != raw:
            raise PathSecurityError(f"{label} storage collision")
        originals[key] = raw
        encoded[raw] = component
    return encoded


def resolve_under(
    root: Path,
    *components: str,
    label: str = "managed path",
) -> Path:
    """Resolve a target below *root*, including existing symlink parents."""

    resolved_root = Path(root).expanduser().resolve()
    candidate = resolved_root
    for component in components:
        text = str(component)
        if (
            not text
            or text in {".", ".."}
            or "\x00" in text
            or "/" in text
            or "\\" in text
            or _DRIVE_PATH.match(text)
        ):
            raise PathSecurityError(f"invalid component in {label}")
        candidate = candidate / text
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise PathSecurityError(f"{label} escapes its managed root") from exc
    return resolved_candidate
