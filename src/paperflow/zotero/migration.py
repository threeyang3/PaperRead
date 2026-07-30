"""Dry-run and result-ingestion helpers for PaperFlow → Zotero migration.

This module produces plans and stores plugin-returned results.  It never writes
Zotero objects and never touches the Zotero database; the Zotero plugin remains
the only writer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from paperflow.paths.templates import safe_component
from paperflow.utils import atomic_json, iso_beijing
from paperflow.zotero.mapping_index import rebuild_mapping_index
from paperflow.zotero.mapping import match_record
from paperflow.zotero.store import data_root


def _records(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    directory = data_root(root) / "papers"
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("paper_uid"):
            result.append(value)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _attachment(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    raw = str(record.get("paper_pdf_path") or "").strip()
    if not raw:
        return {"status": "missing", "source_path": "", "sha256": ""}
    path = root / raw
    if not path.is_file():
        return {"status": "missing", "source_path": raw, "sha256": ""}
    return {"status": "ready", "source_path": raw, "sha256": _sha256(path)}


def plan_migration(
    root: Path,
    items: Iterable[dict[str, Any]],
    *,
    collection_name: str = "PaperFlow",
    paper_uid: str = "",
    attachment_mode: str = "stored",
) -> dict[str, Any]:
    if attachment_mode not in {"stored", "linked"}:
        raise ValueError("attachment_mode must be stored or linked")
    records = [record for record in _records(root) if not paper_uid or record.get("paper_uid") == paper_uid]
    zotero_items = list(items)
    plans: list[dict[str, Any]] = []
    for record in records:
        candidates = [match_record(record, item) for item in zotero_items]
        candidates = [candidate for candidate in candidates if candidate.zotero_key]
        candidates.sort(key=lambda value: (-value.score, value.zotero_key))
        best = candidates[0] if candidates else None
        tied = [value for value in candidates if best and value.score == best.score]
        unique = best if best and len(tied) == 1 else None
        attachment = _attachment(root, record)
        plans.append(
            {
                "paper_uid": record["paper_uid"],
                "title": record.get("paper_title_display") or record.get("paper_title") or "",
                "identity": unique.model_dump() if unique else None,
                "identity_status": unique.status if unique else "manual-review",
                "item_action": "reuse" if unique and unique.status == "exact" else "create-via-plugin",
                "collection_action": "add-membership",
                "collection_name": collection_name,
                "attachment": {**attachment, "mode": attachment_mode},
                "warnings": (["pdf-not-found"] if attachment["status"] == "missing" else []),
            }
        )
    return {
        "schema_version": 1,
        "dry_run": True,
        "created_at": iso_beijing(),
        "collection_name": collection_name,
        "attachment_mode": attachment_mode,
        "papers": plans,
        "counts": {
            "total": len(plans),
            "exact_reuse": sum(item["item_action"] == "reuse" for item in plans),
            "create_via_plugin": sum(item["item_action"] == "create-via-plugin" for item in plans),
            "manual_review": sum(item["identity_status"] == "manual-review" for item in plans),
            "missing_pdf": sum("pdf-not-found" in item["warnings"] for item in plans),
        },
        "policy": "plan-only; Zotero writes must be performed by the PaperFlow Zotero plugin",
    }


def ingest_plugin_results(root: Path, results: dict[str, Any]) -> dict[str, Any]:
    """Persist validated plugin results as mappings; no Zotero write occurs."""
    if not isinstance(results, dict) or not isinstance(results.get("items"), list):
        raise ValueError("plugin results must contain an items list")
    written: list[str] = []
    rejected: list[dict[str, Any]] = []
    for item in results["items"]:
        if not isinstance(item, dict):
            rejected.append({"reason": "item-not-object"})
            continue
        paper_uid = str(item.get("paper_uid") or "").strip()
        zotero_key = str(item.get("item_key") or "").strip()
        if not paper_uid or not zotero_key or any(char in paper_uid + zotero_key for char in "\\/\x00"):
            rejected.append({"paper_uid": paper_uid, "reason": "missing-or-invalid-identity"})
            continue
        attachments = []
        invalid_attachment = False
        for attachment in item.get("attachments") or []:
            if not isinstance(attachment, dict):
                invalid_attachment = True
                break
            key = str(attachment.get("key") or attachment.get("item_key") or "").strip()
            digest = str(attachment.get("sha256") or "").strip().lower()
            mode = str(attachment.get("mode") or "stored").strip().lower()
            if not key or any(char in key for char in "\\/\x00") or mode not in {"stored", "linked"}:
                invalid_attachment = True
                break
            if digest and (len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)):
                invalid_attachment = True
                break
            attachments.append({**attachment, "key": key, "sha256": digest, "mode": mode})
        if invalid_attachment:
            rejected.append({"paper_uid": paper_uid, "reason": "invalid-attachment-fact"})
            continue
        mapping = {
            "schema_version": 2,
            "paper_uid": paper_uid,
            "zotero": {
                "item_key": zotero_key,
                "library_id": item.get("library_id"),
                "collection_keys": list(item.get("collection_keys") or []),
                "attachments": attachments,
                "attachment_verification": "sha256-verified" if attachments and all(value.get("sha256") for value in attachments) else "pending-file-check",
                "source": "paperflow-zotero-plugin",
                "updated_at": iso_beijing(),
            },
        }
        mapping_root = root / "data/connectors/zotero/mappings" if (root / "data").is_dir() and not (root / ".paperflow").exists() else root / ".paperflow/data/connectors/zotero/mappings"
        path = mapping_root / f"{safe_component(paper_uid.replace(':', '_'))}.json"
        atomic_json(path, mapping)
        written.append(path.relative_to(root).as_posix())
    if written:
        rebuild_mapping_index(root)
    return {
        "schema_version": 1,
        "dry_run": False,
        "status": "applied" if not rejected else "partial",
        "mappings": written,
        "rejected": rejected,
    }


def verify_migration(root: Path) -> dict[str, Any]:
    checked = 0
    valid = 0
    issues: list[dict[str, str]] = []
    directory = root / "data/connectors/zotero/mappings" if (root / "data").is_dir() and not (root / ".paperflow").exists() else root / ".paperflow/data/connectors/zotero/mappings"
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        checked += 1
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append({"path": path.relative_to(root).as_posix(), "reason": str(exc)})
            continue
        if not value.get("paper_uid") or not value.get("zotero", {}).get("item_key"):
            issues.append({"path": path.relative_to(root).as_posix(), "reason": "incomplete mapping"})
            continue
        valid += 1
    return {"ok": not issues, "checked": checked, "valid": valid, "issues": issues}


__all__ = ["ingest_plugin_results", "plan_migration", "verify_migration"]
