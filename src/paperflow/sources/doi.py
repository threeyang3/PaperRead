from __future__ import annotations
from .url_parser import parse_input


def normalize_doi(value: str) -> str:
    parsed = parse_input(value)
    if parsed.kind != "doi":
        raise ValueError("Not a DOI")
    return parsed.doi

