from __future__ import annotations
import re
import time
import uuid
from datetime import datetime
from typing import Any
from pathlib import Path
import feedparser
import httpx
from paperflow.models import PaperMetadata
from paperflow.text_quality import validate_text_quality
from .url_parser import parse_input

API_URL = "https://export.arxiv.org/api/query"


def _date(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


class ArxivSource:
    def __init__(self, timeout: int = 60, retries: int = 3, interval: int = 3, transport: Any = None, cache_dir: Path | None = None):
        self.timeout, self.retries, self.interval, self.transport, self.cache_dir = timeout, retries, interval, transport, cache_dir

    def _query(self, params: dict[str, Any]) -> Any:
        error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True, transport=self.transport, headers={"User-Agent": "PaperFlow/0.1 (local research tool)"}) as client:
                    response = client.get(API_URL, params=params)
                    response.raise_for_status()
                    if self.cache_dir is not None:
                        self.cache_dir.mkdir(parents=True, exist_ok=True)
                        (self.cache_dir / f"response-{int(time.time())}-{uuid.uuid4().hex[:8]}.xml").write_bytes(response.content)
                    # arXiv Atom is UTF-8. Passing decoded text avoids
                    # feedparser/header charset guesses on Windows locales.
                    xml = response.content.decode("utf-8-sig", errors="strict")
                    return feedparser.parse(xml)
            except Exception as exc:
                error = exc
                if attempt + 1 < self.retries:
                    time.sleep(self.interval * (attempt + 1))
        raise RuntimeError(f"arXiv API failed: {error}")

    def fetch(self, value: str) -> PaperMetadata:
        parsed = parse_input(value)
        if parsed.kind != "arxiv":
            raise ValueError("ArxivSource requires an arXiv input")
        feed = self._query({"id_list": parsed.arxiv_id, "max_results": 1})
        if not feed.entries:
            raise LookupError(f"arXiv paper not found: {parsed.arxiv_id}")
        return self._entry_to_metadata(feed.entries[0], parsed.arxiv_id, parsed.version)

    @staticmethod
    def _entry_to_metadata(e: Any, fallback_id: str = "", fallback_version: int = 1) -> PaperMetadata:
        match = re.search(r"v(\d+)$", e.id)
        id_match = re.search(r"/(?:abs|pdf)/(.+?)(?:v\d+)?(?:\.pdf)?$", e.id)
        arxiv_id = id_match.group(1) if id_match else fallback_id
        version = int(match.group(1)) if match else fallback_version
        authors = [a.name for a in e.authors]
        categories = [t.term for t in e.tags]
        pdf_url = next((l.href for l in e.links if getattr(l, "type", "") == "application/pdf"), f"https://arxiv.org/pdf/{arxiv_id}")
        metadata = PaperMetadata(
            paper_uid=f"arxiv:{arxiv_id}", paper_arxiv_id=arxiv_id,
            paper_arxiv_version=version, paper_title=" ".join(e.title.split()), paper_authors=authors,
            paper_first_author=authors[0] if authors else "", paper_year=_date(e.published).year,
            paper_submitted_date=_date(e.published), paper_updated_date=_date(e.updated),
            paper_primary_category=getattr(e, "arxiv_primary_category", {}).get("term", categories[0] if categories else ""),
            paper_categories=categories, paper_abstract=" ".join(e.summary.split()), paper_pdf_url=pdf_url,
            paper_abs_url=f"https://arxiv.org/abs/{arxiv_id}v{version}",
            paper_doi=getattr(e, "arxiv_doi", "") or "", paper_published_venue=getattr(e, "arxiv_journal_ref", "") or "",
        )
        validate_text_quality(metadata.model_dump(mode="json"), label="arxiv")
        return metadata

    def discover(self, query: str, max_results: int = 100) -> list[PaperMetadata]:
        feed = self._query({"search_query": query, "start": 0, "max_results": max_results, "sortBy": "lastUpdatedDate", "sortOrder": "descending"})
        return [self._entry_to_metadata(entry) for entry in feed.entries]
