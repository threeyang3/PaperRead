from __future__ import annotations
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ARXIV_RE = re.compile(r"(?<!\d)(?P<id>(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7}))(?:v(?P<version>\d+))?(?!\d)", re.I)
DOI_RE = re.compile(r"(?:https?://(?:dx\.)?doi\.org/)?(?P<doi>10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.I)


@dataclass(frozen=True)
class ParsedInput:
    kind: str
    canonical: str
    arxiv_id: str = ""
    version: int = 1
    doi: str = ""


def normalize_url(value: str) -> str:
    value = value.strip()
    parts = urlsplit(value)
    if not parts.scheme:
        return value
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    host = parts.netloc.lower()
    scheme = parts.scheme.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


def parse_input(value: str) -> ParsedInput:
    value = value.strip()
    arxiv = ARXIV_RE.search(value)
    if arxiv and ("arxiv" in value.lower() or value.lower().endswith(".pdf") or value == arxiv.group(0)):
        base = arxiv.group("id")
        version = int(arxiv.group("version") or 1)
        return ParsedInput("arxiv", f"https://arxiv.org/abs/{base}v{version}", base, version)
    doi = DOI_RE.search(value)
    if doi:
        normalized = doi.group("doi").rstrip(".,;").lower()
        return ParsedInput("doi", f"https://doi.org/{normalized}", doi=normalized)
    if value.lower().startswith(("http://", "https://")):
        canonical = normalize_url(value)
        kind = "pdf" if urlsplit(canonical).path.lower().endswith(".pdf") else "url"
        return ParsedInput(kind, canonical)
    raise ValueError(f"Unsupported paper input: {value}")

