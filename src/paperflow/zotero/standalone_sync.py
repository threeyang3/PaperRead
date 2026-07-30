"""Subscription and community ingestion for a standalone Core data root.

The Vault subscriber predates the Zotero-first Core and therefore writes into
``.paperflow``/Obsidian paths.  This module keeps the same feed contract while
using only the standalone layout and never opening or modifying a Zotero
database.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx
from ruamel.yaml import YAML

from paperflow.community.models import CommunityContribution
from paperflow.community.privacy import scan_community_contribution
from paperflow.community.publisher import verify_content_sha256
from paperflow.community.subscriber import community_rating_summary, render_community_note
from paperflow.feed.publisher import resolve_feed_file, validate_feed
from paperflow.feed.subscriber import _acquire, _sha256
from paperflow.security.artifacts import PermissionGuard
from paperflow.versioning import check_reader_version
from paperflow.zotero.store import data_root
from paperflow.zotero.mapping_index import mapping_for_paper
from paperflow.utils import atomic_json, iso_beijing


def _paper_id(value: str) -> str:
    return str(value).replace(":", "_").replace("/", "_")


def _copy_verified(source: Path, target: Path, expected_sha256: str) -> tuple[str, bool]:
    source_hash = _sha256(source)
    if expected_sha256 and source_hash != expected_sha256:
        raise ValueError(f"Manifest hash mismatch: {source}")
    if target.is_file():
        if _sha256(target) == source_hash:
            return target.as_posix(), False
        target = target.with_name(target.stem + "-conflict" + target.suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    shutil.copy2(source, temporary)
    temporary.replace(target)
    return target.as_posix(), True


def _download_pdf(root: Path, item: dict[str, Any]) -> bool:
    pdf = item.get("pdf") or {}
    source_url = str(pdf.get("source_url") or "")
    if not source_url:
        return False
    paper_id = _paper_id(str(item.get("source_id") or item["paper_uid"]))
    target = root / "documents/zotero" / f"{paper_id}.pdf"
    if target.exists():
        if target.read_bytes()[:5] != b"%PDF-":
            raise ValueError(f"Existing PDF has an invalid header: {target}")
        expected = str(pdf.get("expected_sha256") or "")
        if expected and _sha256(target) != expected:
            raise ValueError(f"Existing PDF checksum mismatch: {target}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    digest = hashlib.sha256()
    size = 0
    try:
        with httpx.stream("GET", source_url, timeout=60, follow_redirects=True) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes():
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)
        if temporary.read_bytes()[:5] != b"%PDF-":
            raise ValueError(f"Downloaded file is not a PDF: {source_url}")
        expected = str(pdf.get("expected_sha256") or "")
        if expected and digest.hexdigest() != expected:
            raise ValueError(f"Downloaded PDF checksum mismatch: {source_url}")
        expected_size = pdf.get("expected_size")
        if expected_size is not None and size != int(expected_size):
            raise ValueError(f"Downloaded PDF size mismatch: {source_url}")
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return True


def _zotero_mapping_exists(root: Path, paper_uid: str) -> bool:
    value = mapping_for_paper(root, paper_uid)
    return bool(value and (value.get("zotero") or {}).get("item_key"))


def _update_subscription_inbox(
    root: Path,
    item: dict[str, Any],
    *,
    feed_id: str,
    source_path: str,
    source_sha256: str,
) -> str:
    """Create a durable, metadata-only handoff for papers absent from Zotero.

    The inbox is a system-managed projection.  A user's decision is preserved
    across refreshes; only a still-pending record may move between ``linked``
    and ``pending-confirmation`` as a mapping appears or disappears.
    """

    paper_uid = str(item.get("paper_uid") or "").strip()
    if not paper_uid:
        raise ValueError("subscription item is missing paper_uid")
    inbox_root = data_root(root) / "subscriptions/inbox"
    target = inbox_root / f"{_paper_id(paper_uid)}.json"
    existing: dict[str, Any] = {}
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}
    old_status = str(existing.get("status") or "")
    if old_status in {"imported", "dismissed"}:
        status = old_status
    else:
        status = "linked" if _zotero_mapping_exists(root, paper_uid) else "pending-confirmation"
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else item
    value = {
        "schema_version": 1,
        "artifact_permission": "REMOTE_READ_ONLY",
        "paper_uid": paper_uid,
        "title": str(metadata.get("paper_title_display") or metadata.get("paper_title") or item.get("title") or ""),
        "authors": metadata.get("paper_authors") or metadata.get("authors") or [],
        "abstract": str(metadata.get("paper_abstract") or metadata.get("abstract") or ""),
        "url": str(metadata.get("paper_abs_url") or metadata.get("paper_pdf_url") or item.get("url") or ""),
        "source": str(item.get("source") or ""),
        "source_id": str(item.get("source_id") or ""),
        "source_version": int(item.get("version") or item.get("source_version") or 1),
        "feed_id": feed_id,
        "source_path": source_path,
        "source_sha256": source_sha256,
        "pdf": item.get("pdf") if isinstance(item.get("pdf"), dict) else {},
        "status": status,
        "created_at": str(existing.get("created_at") or iso_beijing()),
        "updated_at": iso_beijing(),
    }
    for key in ("decision_at", "zotero_item_key", "decision_note"):
        if key in existing:
            value[key] = existing[key]
    PermissionGuard(root).authorize(target, "SYSTEM_MANAGED")
    atomic_json(target, value)
    return status


def _ingest_community(
    root: Path,
    feed_root: Path,
    feed_id: str,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    files = sorted(feed_root.glob("papers/*/community/*/*/r*.json"))
    accepted: list[CommunityContribution] = []
    planned: list[str] = []
    for source in files:
        value = CommunityContribution.model_validate_json(source.read_text(encoding="utf-8"))
        normalized = value.model_dump(mode="json")
        if not verify_content_sha256(normalized):
            raise ValueError(f"{source}: content_sha256 mismatch")
        findings = scan_community_contribution(normalized)
        if findings:
            raise ValueError(f"{source}: {findings}")
        relative = source.relative_to(feed_root)
        target = root / "data/community/subscriptions" / feed_id / relative
        planned.append(target.relative_to(root).as_posix())
        accepted.append(value)
        if not dry_run:
            PermissionGuard(root).authorize(target, "SYSTEM_MANAGED")
            atomic_json(target, normalized)

    cache_root = root / "data/community/subscriptions"
    if not dry_run and cache_root.exists():
        candidates = [
            CommunityContribution.model_validate_json(path.read_text(encoding="utf-8"))
            for path in cache_root.glob("*/papers/*/community/*/*/r*.json")
        ]
    else:
        candidates = accepted
    latest: dict[tuple[str, str], CommunityContribution] = {}
    for item in candidates:
        key = (item.creator, item.contribution_id)
        if item.paper_uid and (key not in latest or item.revision > latest[key].revision):
            latest[key] = item

    rendered: list[dict[str, Any]] = []
    for paper_uid in sorted({item.paper_uid for item in latest.values()}):
        paper_id = _paper_id(paper_uid)
        output = root / "documents/zotero" / f"{paper_id}.community.md"
        rendered.append(
            render_community_note(
                root,
                paper_uid,
                list(latest.values()),
                output,
                dry_run=dry_run,
                paper_title=paper_uid,
                pdf_path=f"documents/zotero/{paper_id}.pdf",
            )
        )
    return {
        "dry_run": dry_run,
        "feed_id": feed_id,
        "accepted": len(accepted),
        "paths": planned,
        "ratings": community_rating_summary(accepted),
        "rendered_notes": rendered,
        "private_user_records_modified": 0,
        "remote_code_executed": False,
    }


def sync_core_feed(
    root: Path,
    *,
    url: str,
    name: str,
    branch: str = "main",
    trust: str = "metadata-and-ai",
    dry_run: bool = False,
    auto_download_pdf: bool = False,
    auto_render_notes: bool = False,
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Synchronize one validated feed into a standalone Core root."""

    if trust not in {"metadata-only", "metadata-and-ai", "disabled"}:
        raise ValueError(f"Unsupported trust mode: {trust}")
    if trust == "disabled":
        return {"name": name, "status": "disabled", "created": 0, "conflicts": []}
    root = root.resolve()
    with TemporaryDirectory(prefix="paperflow-core-feed-") as temporary:
        feed_root = _acquire(url, branch, Path(temporary) / "feed")
        validation = validate_feed(feed_root)
        feed = YAML(typ="safe").load((feed_root / "feed.yaml").read_text(encoding="utf-8"))
        check_reader_version(str(feed["minimum_reader_version"]))
        feed_id = str(feed["feed_id"])
        advertised = feed.get("capabilities") or {"raw": True, "ai": True, "community": False}
        requested = set(capabilities or ["raw", "ai"])
        enabled = {value for value in requested if advertised.get(value, False)}
        manifests = [
            json.loads(line)
            for line in (feed_root / "manifests/papers.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        if trust == "metadata-and-ai" and "ai" in enabled:
            analysis_manifest = feed_root / "manifests/analyses.jsonl"
            if analysis_manifest.is_file():
                manifests.extend(json.loads(line) for line in analysis_manifest.read_text(encoding="utf-8").splitlines() if line)

        created = 0
        reused = 0
        conflicts: list[dict[str, str]] = []
        raw_items: list[dict[str, Any]] = []
        inbox_statuses: list[str] = []
        for item in manifests:
            source = resolve_feed_file(feed_root, item["path"])
            expected = str(item.get("sha256") or "")
            is_ai = "analysis_id" in item
            paper_id = _paper_id(str(item["paper_uid"]))
            if is_ai:
                target = root / "data/ai/subscriptions" / feed_id / paper_id / f"{item['analysis_id']}.json"
            else:
                target = root / "data/raw/subscriptions" / feed_id / paper_id / f"v{item['version']}.json"
                raw_items.append(item)
            target_path, wrote = _copy_verified(source, target, expected)
            if wrote:
                created += 1
            else:
                reused += 1
            if "conflict" in Path(target_path).name:
                conflicts.append({"paper_uid": str(item["paper_uid"]), "target": str(target_path), "policy": "preserve-both"})

            if not dry_run and not is_ai:
                raw = json.loads(source.read_text(encoding="utf-8"))
                metadata = dict(raw.get("metadata") or raw)
                metadata["paper_uid"] = str(item["paper_uid"])
                metadata.setdefault("paper_arxiv_id", str(item.get("source_id") or "").removeprefix("arxiv_"))
                paper_target = root / "data/papers" / f"{paper_id}.json"
                if not paper_target.exists():
                    PermissionGuard(root).authorize(paper_target, "RAW_VERSIONED")
                    atomic_json(paper_target, metadata)
                inbox_statuses.append(_update_subscription_inbox(
                    root,
                    {**item, "metadata": metadata},
                    feed_id=feed_id,
                    source_path=source.relative_to(feed_root).as_posix(),
                    source_sha256=expected or _sha256(source),
                ))

        downloaded = sum(_download_pdf(root, item) for item in raw_items) if not dry_run and auto_download_pdf else 0
        rendered_notes = 0
        if not dry_run and auto_render_notes:
            from paperflow.zotero.markdown import render_ai_projection

            for item in raw_items:
                render_ai_projection(root, str(item["paper_uid"]), target="zotero", apply_changes=True)
                rendered_notes += 1
        community = {"dry_run": dry_run, "accepted": 0, "private_user_records_modified": 0}
        if "community" in enabled:
            community = _ingest_community(root, feed_root, feed_id, dry_run=dry_run)
        return {
            "name": name,
            "feed_id": feed_id,
            "trust": trust,
            "dry_run": dry_run,
            "created": created,
            "reused": reused,
            "conflicts": conflicts,
            "downloaded_pdfs": downloaded,
            "rendered_notes": rendered_notes,
            "subscription_inbox": {
                "total": len(inbox_statuses),
                "pending_confirmation": inbox_statuses.count("pending-confirmation"),
                "linked": inbox_statuses.count("linked"),
                "imported": inbox_statuses.count("imported"),
                "dismissed": inbox_statuses.count("dismissed"),
            },
            "remote_code_executed": False,
            "validation": validation,
            "feed_schema_version": int(feed.get("feed_schema_version", 1)),
            "capabilities": sorted(enabled),
            "community": community,
        }


__all__ = ["sync_core_feed"]
