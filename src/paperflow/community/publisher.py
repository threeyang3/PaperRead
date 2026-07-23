from __future__ import annotations

import hashlib
import hmac
import json
import shutil
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from paperflow.community.models import CommunityContribution
from paperflow.annotations.models import Annotation, PaperReview
from paperflow.community.privacy import scan_community_contribution
from paperflow.utils import atomic_json, iso_beijing


def canonical_content_sha256(value: dict[str, Any]) -> str:
    """Hash the public payload using the publisher's canonical JSON contract."""
    payload = dict(value)
    payload.pop("content_sha256", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_content_sha256(value: dict[str, Any]) -> bool:
    expected = str(value.get("content_sha256") or "")
    return bool(expected) and hmac.compare_digest(
        expected,
        canonical_content_sha256(value),
    )


def normalize_private_contribution(source: dict[str, Any]) -> dict[str, Any]:
    """Project a private annotation/review into the explicitly public contract."""
    source_type = str(source.get("type") or "")
    if source_type == "paperflow-user-annotation":
        annotation = Annotation.model_validate(source)
        revision = annotation.preferred_revision
        quote = revision.anchor.text_quote_selector
        return {
            "contribution_id": annotation.annotation_id,
            "paper_uid": annotation.paper_uid,
            "kind": annotation.kind,
            "body": annotation.body,
            "tags": annotation.tags,
            "created_at": annotation.created_at,
            "anchor": {
                "pdf_version": revision.anchor.pdf_version,
                "pdf_sha256": revision.anchor.pdf_sha256,
                "page": revision.anchor.page,
                "exact_quote": (quote.exact if quote else "")[:500],
                "prefix": (quote.prefix if quote else "")[:120],
                "suffix": (quote.suffix if quote else "")[:120],
            },
        }
    if source_type == "paperflow-user-paper-review":
        review = PaperReview.model_validate(source)
        sections = [
            ("摘要", review.summary),
            ("优点", review.strengths),
            ("局限", review.weaknesses),
            ("问题", review.questions),
            ("复现笔记", review.reproduction_notes),
            ("结论", review.verdict),
        ]
        return {
            "contribution_id": review.review_id,
            "paper_uid": review.paper_uid,
            "kind": "paper-review",
            "body": "\n\n".join(
                f"### {heading}\n\n{body}" for heading, body in sections if body
            ),
            "tags": [],
            "rating": review.rating,
            "anchor": None,
            "created_at": review.created_at,
        }
    if source_type == "paperflow-community-draft":
        return source
    raise ValueError(f"Unsupported private contribution type: {source_type or 'missing'}")


def immutable_snapshot(
    source: dict[str, Any],
    *,
    creator: str,
    license_name: str,
    revision: int = 1,
    supersedes: str = "",
) -> CommunityContribution:
    public = {
        "type": "paperflow-community-contribution",
        "community_data_schema_version": 1,
        "contribution_id": str(source["contribution_id"]),
        "revision": revision,
        "supersedes": supersedes,
        "paper_uid": str(source["paper_uid"]),
        "creator": creator,
        "kind": str(source["kind"]),
        "body": str(source.get("body", "")),
        "tags": list(source.get("tags", [])),
        "rating": source.get("rating"),
        "anchor": source.get("anchor"),
        "license": license_name,
        "created_at": str(source.get("created_at") or iso_beijing()),
        "extensions": dict(source.get("extensions") or {}),
    }
    public["content_sha256"] = ""
    normalized = CommunityContribution.model_validate(public).model_dump(mode="json")
    normalized["content_sha256"] = canonical_content_sha256(normalized)
    contribution = CommunityContribution.model_validate(normalized)
    findings = scan_community_contribution(contribution.model_dump(mode="json"))
    if findings:
        raise ValueError("Community privacy scan failed: " + ", ".join(findings))
    return contribution


def build_outbox(
    vault: Path,
    contribution: CommunityContribution,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    paper_id = contribution.paper_uid.replace(":", "_")
    relative = (
        Path("papers") / paper_id / "community" / contribution.creator
        / contribution.contribution_id / f"r{contribution.revision}.json"
    )
    target = vault / ".paperflow/data/community/outbox" / relative
    result = {
        "dry_run": dry_run,
        "path": relative.as_posix(),
        "creator": contribution.creator,
        "license": contribution.license,
        "quote": (contribution.anchor.exact_quote if contribution.anchor else ""),
        "rating": contribution.rating,
        "privacy_scan": "passed",
        "git_actions": ["fork", "branch", "commit", "pull-request"],
        "network_changes": 0,
    }
    if not dry_run:
        atomic_json(target, contribution.model_dump(mode="json"))
    return result


def build_pr_tree(vault: Path, destination: Path, *, dry_run: bool = True) -> dict[str, Any]:
    outbox = vault / ".paperflow/data/community/outbox"
    files = sorted(outbox.rglob("r*.json"))
    planned = []
    for source in files:
        value = CommunityContribution.model_validate_json(source.read_text(encoding="utf-8"))
        findings = scan_community_contribution(value.model_dump(mode="json"))
        if findings:
            raise ValueError(f"{source}: {findings}")
        relative = source.relative_to(outbox)
        planned.append(relative.as_posix())
        if not dry_run:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return {"dry_run": dry_run, "files": planned, "network_changes": 0}
