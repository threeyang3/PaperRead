from __future__ import annotations

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import unquote, urlparse

from ruamel.yaml import YAML
from paperflow.feed.publisher import resolve_feed_file, validate_feed
from paperflow.feed.conflicts import copy_preserving_conflicts
from paperflow.net.pdf_download import download_pdf_safely
from paperflow.security.paths import (
    assert_distinct_storage_components,
    encode_storage_component_v2,
    resolve_under,
    safe_storage_component,
)
from paperflow.versioning import check_reader_version
from paperflow.sync_safety import assert_no_sync_conflicts

MAX_LINKED_PDF_BYTES = 100 * 1024 * 1024


def _sha256(path: Path) -> str:
    from paperflow.feed.conflicts import sha256_file

    return sha256_file(path)


def _local_source(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return (
            Path(unquote(parsed.path.lstrip("/"))) if parsed.netloc else Path(unquote(parsed.path))
        )
    candidate = Path(url)
    return candidate.resolve() if candidate.exists() else None


def _acquire(url: str, branch: str, destination: Path) -> Path:
    local = _local_source(url)
    if local is not None:
        return local
    command = [
        "git",
        "-c",
        "core.hooksPath=NUL",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--branch",
        branch,
        "--",
        url,
        str(destination),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Feed clone failed: {result.stderr[-500:]}")
    return destination


def inspect_feed(url: str, branch: str = "main") -> dict[str, Any]:
    with TemporaryDirectory(prefix="paperflow-feed-") as temporary:
        root = _acquire(url, branch, Path(temporary) / "feed")
        validation = validate_feed(root)
        metadata = YAML(typ="safe").load((root / "feed.yaml").read_text(encoding="utf-8"))
        check_reader_version(str(metadata["minimum_reader_version"]))
        return {"feed": metadata, "validation": validation}


def sync_feed(
    workspace: Path,
    *,
    url: str,
    name: str,
    branch: str = "main",
    trust: str = "metadata-and-ai",
    dry_run: bool = False,
    auto_download_pdf: bool = False,
    auto_render_notes: bool = False,
    capabilities: list[str] | None = None,
    community_note_root: str = "70 Community",
    cancellation_token: Any | None = None,
) -> dict[str, Any]:
    if cancellation_token is not None:
        cancellation_token.raise_if_cancelled()
    assert_no_sync_conflicts(workspace)
    if trust not in {"metadata-only", "metadata-and-ai", "disabled"}:
        raise ValueError(f"Unsupported trust mode: {trust}")
    if trust == "disabled":
        return {"name": name, "status": "disabled", "created": 0, "conflicts": []}
    with TemporaryDirectory(prefix="paperflow-feed-") as temporary:
        feed_root = _acquire(url, branch, Path(temporary) / "feed")
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled(side_effects=True)
        validation = validate_feed(feed_root)
        feed = YAML(typ="safe").load((feed_root / "feed.yaml").read_text(encoding="utf-8"))
        feed_version = int(feed.get("feed_schema_version", 1))
        requested_capabilities = set(capabilities or ["raw", "ai"])
        advertised = feed.get("capabilities") or {
            "raw": True,
            "ai": True,
            "community": False,
        }
        enabled_capabilities = {
            name for name in requested_capabilities if advertised.get(name, False)
        }
        manifests = [
            json.loads(line)
            for line in (feed_root / "manifests/papers.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        if trust == "metadata-and-ai" and "ai" in enabled_capabilities:
            manifests.extend(
                json.loads(line)
                for line in (feed_root / "manifests/analyses.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line
            )
        feed_component = safe_storage_component(feed["feed_id"], label="feed_id")
        paper_components = assert_distinct_storage_components(
            [item["paper_uid"] for item in manifests], label="paper_uid"
        )
        analysis_components = assert_distinct_storage_components(
            [item["analysis_id"] for item in manifests if "analysis_id" in item],
            label="analysis_id",
        )
        created = 0
        reused = 0
        downloaded_pdfs = 0
        rendered_notes = 0
        conflicts: list[dict[str, str]] = []
        for item in manifests:
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            source = resolve_feed_file(feed_root, item["path"])
            if _sha256(source) != item["sha256"]:
                raise ValueError(f"Manifest hash mismatch: {item['path']}")
            is_ai = "analysis_id" in item
            paper_component = paper_components[str(item["paper_uid"])]
            if is_ai:
                target = resolve_under(
                    workspace / ".paperflow/data/ai/subscriptions",
                    feed_component,
                    paper_component,
                    f"{analysis_components[str(item['analysis_id'])]}.json",
                    label="Feed AI subscription path",
                )
            else:
                version = int(item["version"])
                if version < 1:
                    raise ValueError("Feed paper version must be positive")
                target = resolve_under(
                    workspace / ".paperflow/data/raw/subscriptions",
                    feed_component,
                    paper_component,
                    f"v{version}.json",
                    label="Feed Raw subscription path",
                )
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            outcome = copy_preserving_conflicts(
                source,
                target,
                source_id=feed_component,
                expected_sha256=str(item["sha256"]),
                dry_run=dry_run,
            )
            if outcome.status in {"created", "conflict-created"}:
                created += 1
            else:
                reused += 1
            if outcome.status.startswith("conflict-"):
                conflicts.append(
                    {
                        "paper_uid": str(item["paper_uid"]),
                        "target": outcome.path.relative_to(workspace).as_posix(),
                        "policy": "preserve-both",
                        "status": outcome.status,
                        "sha256": outcome.sha256,
                    }
                )
        if not dry_run:
            paper_items = [item for item in manifests if "analysis_id" not in item]
            if auto_download_pdf:
                for item in paper_items:
                    if _download_linked_pdf(workspace, item, cancellation_token=cancellation_token):
                        downloaded_pdfs += 1
            if auto_render_notes:
                for item in paper_items:
                    _render_local_note(
                        workspace,
                        feed_root,
                        item,
                        feed_id=str(feed["feed_id"]),
                    )
                    rendered_notes += 1
        community = {
            "dry_run": dry_run,
            "accepted": 0,
            "private_user_records_modified": 0,
        }
        if "community" in enabled_capabilities:
            from paperflow.community.subscriber import ingest_community

            community = ingest_community(
                workspace,
                feed_root,
                str(feed["feed_id"]),
                dry_run=dry_run,
                community_note_root=community_note_root,
            )
        return {
            "name": name,
            "feed_id": feed["feed_id"],
            "trust": trust,
            "dry_run": dry_run,
            "created": created,
            "reused": reused,
            "conflicts": conflicts,
            "downloaded_pdfs": downloaded_pdfs,
            "rendered_notes": rendered_notes,
            "user_records_modified": 0,
            "remote_code_executed": False,
            "validation": validation,
            "feed_schema_version": feed_version,
            "capabilities": sorted(enabled_capabilities),
            "community": community,
        }


def _download_linked_pdf(
    workspace: Path,
    item: dict[str, Any],
    *,
    cancellation_token: Any | None = None,
) -> bool:
    pdf = item.get("pdf") or {}
    source_url = str(pdf.get("source_url") or "")
    if not source_url:
        return False
    paper_id = encode_storage_component_v2(
        item.get("source_id") or item["paper_uid"], label="source_id"
    )
    year = safe_storage_component(item.get("year") or "Unclassified", label="paper year")
    version = int(item.get("version") or 1)
    target = resolve_under(
        workspace / "80 Attachments/Papers",
        year,
        paper_id,
        f"v{version}.pdf",
        label="linked PDF path",
    )
    expected_size = pdf.get("expected_size")
    result = download_pdf_safely(
        source_url,
        target,
        expected_sha256=str(pdf.get("expected_sha256") or ""),
        expected_size=int(expected_size) if expected_size is not None else None,
        maximum_size=MAX_LINKED_PDF_BYTES,
        cancellation_token=cancellation_token,
    )
    return result.status == "created"


def _render_local_note(
    workspace: Path,
    feed_root: Path,
    item: dict[str, Any],
    *,
    feed_id: str,
) -> Path:
    from paperflow.config import load_config
    from paperflow.data.compose import compose_record
    from paperflow.obsidian.note_renderer import render_paper
    from paperflow.paths.service import preview_record_paths
    from paperflow.pipeline.import_paper import pending_analysis
    from paperflow.workspace import load_workspace_settings

    raw = json.loads(resolve_feed_file(feed_root, item["path"]).read_text(encoding="utf-8"))
    record = {**raw["metadata"], **pending_analysis()}
    record["paper_uid"] = raw["paper_uid"]
    analyses = [
        json.loads(line)
        for line in (feed_root / "manifests/analyses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and json.loads(line).get("paper_uid") == raw["paper_uid"]
    ]
    selected_analysis = None
    if analyses:
        selected = analyses[-1]
        selected_analysis = json.loads(
            resolve_feed_file(feed_root, selected["path"]).read_text(encoding="utf-8")
        )
        record.update(selected_analysis["analysis"])
        record["system_selected_analysis_id"] = selected_analysis["analysis_id"]
        record["system_selected_analysis_publisher"] = feed_id
        record["ai_analysis_provider"] = selected_analysis["identity"].get("provider", "")
        record["ai_analysis_model"] = selected_analysis["identity"].get("model", "")
        record["ai_analysis_prompt_version"] = selected_analysis["identity"].get(
            "prompt_version", ""
        )
        record["ai_analyzed_at"] = selected_analysis.get("created_at", "")
    cfg = load_config(workspace)
    record = compose_record(
        workspace,
        raw,
        analysis=selected_analysis,
        overlay=record,
    )
    paper_id = encode_storage_component_v2(
        raw.get("source_id") or raw["paper_uid"], label="source_id"
    )
    record.setdefault("paper_arxiv_id", paper_id.removeprefix("arxiv_"))
    record.setdefault("paper_title", paper_id)
    record.setdefault("paper_authors", [])
    record.setdefault("paper_first_author", "")
    for key in [
        "paper_abs_url",
        "paper_project_url",
        "paper_code_url",
        "paper_dataset_url",
        "ai_analysis_provider",
        "ai_analysis_model",
        "ai_analysis_prompt_version",
        "ai_analyzed_at",
    ]:
        record.setdefault(key, "")
    # Keep subscriptions on the same readable filename contract as manual
    # imports and the formal path migration.  Hard-coding ``{paper_id}.md``
    # here used to reintroduce ID-only notes after a migration.
    _, settings = load_workspace_settings(workspace)
    note = workspace / preview_record_paths(workspace, settings, record)["note"]["new_path"]
    if not record.get("paper_pdf_path"):
        year = encode_storage_component_v2(
            raw.get("year") or raw.get("metadata", {}).get("paper_year") or "Unclassified",
            label="paper year",
        )
        version = int(raw.get("source_version") or raw.get("version") or 1)
        pdf = resolve_under(
            workspace / "80 Attachments/Papers",
            year,
            paper_id,
            f"v{version}.pdf",
            label="linked PDF path",
        )
        record["paper_pdf_path"] = pdf.relative_to(workspace).as_posix() if pdf.is_file() else ""
    record.setdefault("paper_has_code", bool(record["paper_code_url"]))
    record.setdefault("paper_has_dataset", bool(record["paper_dataset_url"]))
    record.setdefault(
        "version_change_note",
        f"Imported from PaperFlow Feed {feed_id}.",
    )
    return render_paper(
        workspace,
        record,
        note,
        import_method=f"feed:{feed_id}",
        ui_locale=cfg.ui_locale.locale,
    )
