from __future__ import annotations

import hashlib
import hmac
import json
import shutil
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from paperflow.community.models import CommunityContribution
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
    public["content_sha256"] = canonical_content_sha256(public)
    contribution = CommunityContribution.model_validate(public)
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
