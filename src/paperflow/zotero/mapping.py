"""Deterministic PaperFlow ↔ Zotero identity matching.

The matcher consumes a Zotero JSON export or plugin response.  It never opens
the Zotero database and never merges on title alone without surfacing a manual
review result.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from paperflow.paths.templates import safe_component
from paperflow.utils import atomic_json, iso_beijing
from paperflow.zotero.store import data_root


ARXIV_RE = re.compile(r"(?:arxiv\s*:\s*)?(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_title(value: object) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).casefold()
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def normalize_arxiv_id(value: object) -> str:
    match = ARXIV_RE.search(_text(value))
    return match.group(1) if match else ""


def normalize_doi(value: object) -> str:
    match = DOI_RE.search(_text(value))
    return match.group(0).rstrip(".,;)").casefold() if match else ""


def _authors(value: object) -> list[str]:
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or " ".join(
                    str(item.get(part) or "") for part in ("firstName", "lastName")
                )
            else:
                name = item
            if _text(name):
                names.append(_text(name))
        return names
    return [_text(value)] if _text(value) else []


def _unwrap_item(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("data")
    return value if isinstance(value, dict) else item


@dataclass(frozen=True)
class Match:
    paper_uid: str
    zotero_key: str
    status: str
    score: int
    reasons: tuple[str, ...]

    def model_dump(self) -> dict[str, Any]:
        return {
            "paper_uid": self.paper_uid,
            "zotero_item_key": self.zotero_key,
            "status": self.status,
            "score": self.score,
            "reasons": list(self.reasons),
        }


def match_record(record: dict[str, Any], item: dict[str, Any]) -> Match:
    data = _unwrap_item(item)
    paper_uid = _text(record.get("paper_uid"))
    key = _text(item.get("key") or data.get("key"))
    reasons: list[str] = []
    score = 0
    paper_arxiv = normalize_arxiv_id(record.get("paper_arxiv_id") or paper_uid)
    zotero_arxiv = normalize_arxiv_id(
        data.get("extra") or data.get("url") or data.get("archiveLocation")
    )
    paper_doi = normalize_doi(record.get("paper_doi"))
    zotero_doi = normalize_doi(data.get("DOI") or data.get("doi"))
    if paper_arxiv and paper_arxiv == zotero_arxiv:
        score += 100
        reasons.append("exact-arxiv-id")
    if paper_doi and paper_doi == zotero_doi:
        score += 95
        reasons.append("exact-doi")
    title_equal = normalize_title(record.get("paper_title") or record.get("title")) == normalize_title(data.get("title"))
    if title_equal and normalize_title(data.get("title")):
        score += 45
        reasons.append("normalized-title")
    paper_authors = {_text(value).casefold() for value in _authors(record.get("paper_authors"))}
    zotero_authors = {_text(value).casefold() for value in _authors(data.get("creators"))}
    if paper_authors and zotero_authors and paper_authors & zotero_authors:
        score += 20
        reasons.append("author-overlap")
    if title_equal and paper_authors and zotero_authors and paper_authors & zotero_authors:
        score += 10
        reasons.append("title-author-confirmation")
    status = "exact" if any(reason.startswith("exact-") for reason in reasons) else (
        "candidate" if score >= 55 else "manual-review"
    )
    return Match(paper_uid, key, status, score, tuple(reasons))


def _paper_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((data_root(root) / "papers").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("paper_uid"):
            records.append(value)
    return records


def load_items(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        value = value["items"]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("Zotero input must be a JSON list or {items: [...]}")
    return value


def plan_links(root: Path, items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    zotero_items = list(items)
    plans: list[dict[str, Any]] = []
    for record in _paper_records(root):
        candidates = [match_record(record, item) for item in zotero_items]
        candidates = [candidate for candidate in candidates if candidate.zotero_key]
        candidates.sort(key=lambda candidate: (-candidate.score, candidate.zotero_key))
        best = candidates[0] if candidates else None
        tied = [candidate for candidate in candidates if best and candidate.score == best.score]
        if best and len(tied) == 1:
            plans.append({"paper_uid": record["paper_uid"], "candidate": best.model_dump()})
        else:
            plans.append(
                {
                    "paper_uid": record["paper_uid"],
                    "candidate": None,
                    "status": "manual-review",
                    "reason": "no unique Zotero identity match",
                }
            )
    return {
        "schema_version": 1,
        "dry_run": True,
        "items": len(zotero_items),
        "papers": len(plans),
        "plans": plans,
        "policy": "exact arXiv/DOI first; title-author candidates require review; no database access",
    }


def apply_links(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    mappings: list[str] = []
    manual_review: list[dict[str, Any]] = []
    for item in plan.get("plans", []):
        candidate = item.get("candidate")
        if not candidate or candidate.get("status") != "exact":
            if candidate:
                manual_review.append(item)
            continue
        paper_uid = str(item["paper_uid"])
        mapping_name = safe_component(paper_uid.replace(":", "_"))
        mapping_root = root / "data/connectors/zotero/mappings" if (root / "data").is_dir() and not (root / ".paperflow").exists() else root / ".paperflow/data/connectors/zotero/mappings"
        path = mapping_root / f"{mapping_name}.json"
        atomic_json(
            path,
            {
                "schema_version": 1,
                "paper_uid": paper_uid,
                "zotero": {
                    "item_key": candidate["zotero_item_key"],
                    "source": "paperflow-zotero-link",
                    "matched_at": iso_beijing(),
                    "match": candidate,
                },
            },
        )
        mappings.append(path.relative_to(root).as_posix())
    return {
        **plan,
        "dry_run": False,
        "status": "applied",
        "mappings": mappings,
        "manual_review": manual_review,
    }


__all__ = [
    "Match",
    "apply_links",
    "load_items",
    "match_record",
    "normalize_arxiv_id",
    "normalize_doi",
    "normalize_title",
    "plan_links",
]
