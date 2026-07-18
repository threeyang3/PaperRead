from __future__ import annotations
from dataclasses import dataclass
from paperflow.database import Database
from paperflow.models import PaperMetadata


@dataclass(frozen=True)
class DedupResult:
    action: str
    existing_version: int = 0


def decide(db: Database, metadata: PaperMetadata, force: bool = False) -> DedupResult:
    existing = db.get_paper(metadata.paper_uid)
    if not existing:
        return DedupResult("import")
    old = int(existing["version"] or 1)
    if metadata.paper_arxiv_version > old:
        return DedupResult("update", old)
    return DedupResult("refresh" if force else "skip", old)

