from __future__ import annotations
import hashlib
import re
from datetime import date
from urllib.parse import urlsplit
import httpx
from paperflow.models import PaperMetadata
from .url_parser import ParsedInput

META_RE = re.compile(r'<meta\s+(?:name|property)=["\'](?P<name>citation_[^"\']+|og:title)["\']\s+content=["\'](?P<value>.*?)["\']', re.I)


def _citation_date(value: str):
    for candidate in [value[:10], value[:7] + "-01" if len(value) >= 7 else "", value[:4] + "-01-01" if len(value) >= 4 else ""]:
        try: return date.fromisoformat(candidate)
        except ValueError: pass
    return None


def fetch_generic(parsed: ParsedInput, timeout: int = 60, transport=None) -> PaperMetadata:
    if parsed.kind == "doi":
        with httpx.Client(timeout=timeout, follow_redirects=True, transport=transport, headers={"Accept": "application/vnd.citationstyles.csl+json", "User-Agent": "PaperFlow/0.1"}) as client:
            response = client.get(parsed.canonical)
            response.raise_for_status()
            data = response.json()
        issued = data.get("issued", {}).get("date-parts", [[]])[0]
        year = int(issued[0]) if issued else None
        published = date(year, int(issued[1]) if len(issued) > 1 else 1, int(issued[2]) if len(issued) > 2 else 1) if year else None
        authors = [" ".join(filter(None, [a.get("given", ""), a.get("family", "")])).strip() for a in data.get("author", [])]
        uid = "doi:" + parsed.doi
        venue = data.get("container-title", "") or ""
        return PaperMetadata(paper_uid=uid, paper_source="doi", paper_doi=parsed.doi, paper_title=data.get("title", "") or parsed.doi, paper_authors=authors, paper_first_author=authors[0] if authors else "", paper_year=year, paper_submitted_date=published, paper_updated_date=published, paper_published_venue=venue, paper_abstract=data.get("abstract", "") or "", paper_abs_url=parsed.canonical, paper_pdf_url="")
    if parsed.kind == "pdf":
        title = urlsplit(parsed.canonical).path.rsplit("/", 1)[-1].removesuffix(".pdf")
        digest = hashlib.sha256(parsed.canonical.encode()).hexdigest()[:16]
        return PaperMetadata(paper_uid=f"url:{digest}", paper_source="url", paper_title=title or parsed.canonical, paper_year=None, paper_submitted_date=None, paper_updated_date=None, paper_pdf_url=parsed.canonical, paper_abs_url=parsed.canonical)
    with httpx.Client(timeout=timeout, follow_redirects=True, transport=transport, headers={"User-Agent": "PaperFlow/0.1"}) as client:
        response = client.get(parsed.canonical)
        response.raise_for_status()
    values: dict[str, list[str]] = {}
    for match in META_RE.finditer(response.text):
        values.setdefault(match.group("name").lower(), []).append(match.group("value"))
    title = (values.get("citation_title") or values.get("og:title") or [urlsplit(parsed.canonical).netloc])[0]
    authors = values.get("citation_author", [])
    pdf = (values.get("citation_pdf_url") or [""])[0]
    digest = hashlib.sha256(parsed.canonical.encode()).hexdigest()[:16]
    published = _citation_date((values.get("citation_publication_date") or values.get("citation_date") or [""])[0])
    return PaperMetadata(paper_uid=f"url:{digest}", paper_source="url", paper_title=title, paper_authors=authors, paper_first_author=authors[0] if authors else "", paper_year=published.year if published else None, paper_submitted_date=published, paper_updated_date=published, paper_abstract=(values.get("citation_abstract") or [""])[0], paper_pdf_url=pdf, paper_abs_url=parsed.canonical, paper_project_url=parsed.canonical)
