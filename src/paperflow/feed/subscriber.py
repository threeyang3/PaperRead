from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import unquote, urlparse

from ruamel.yaml import YAML
import httpx

from paperflow.feed.publisher import resolve_feed_file, validate_feed
from paperflow.versioning import check_reader_version


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local_source(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path.lstrip("/"))) if parsed.netloc else Path(unquote(parsed.path))
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
        metadata = YAML(typ="safe").load(
            (root / "feed.yaml").read_text(encoding="utf-8")
        )
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
) -> dict[str, Any]:
    if trust not in {"metadata-only", "metadata-and-ai", "disabled"}:
        raise ValueError(f"Unsupported trust mode: {trust}")
    if trust == "disabled":
        return {"name": name, "status": "disabled", "created": 0, "conflicts": []}
    with TemporaryDirectory(prefix="paperflow-feed-") as temporary:
        feed_root = _acquire(url, branch, Path(temporary) / "feed")
        validation = validate_feed(feed_root)
        feed = YAML(typ="safe").load(
            (feed_root / "feed.yaml").read_text(encoding="utf-8")
        )
        manifests = [
            json.loads(line)
            for line in (feed_root / "manifests/papers.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        if trust == "metadata-and-ai":
            manifests.extend(
                json.loads(line)
                for line in (feed_root / "manifests/analyses.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line
            )
        created = 0
        reused = 0
        downloaded_pdfs = 0
        rendered_notes = 0
        conflicts: list[dict[str, str]] = []
        for item in manifests:
            source = resolve_feed_file(feed_root, item["path"])
            if _sha256(source) != item["sha256"]:
                raise ValueError(f"Manifest hash mismatch: {item['path']}")
            is_ai = "analysis_id" in item
            if is_ai:
                target = (
                    workspace
                    / ".paperflow/data/ai/subscriptions"
                    / str(feed["feed_id"])
                    / str(item["paper_uid"]).replace(":", "_")
                    / f"{item['analysis_id']}.json"
                )
            else:
                target = (
                    workspace
                    / ".paperflow/data/raw"
                    / "subscriptions"
                    / str(feed["feed_id"])
                    / str(item["paper_uid"]).replace(":", "_")
                    / f"v{item['version']}.json"
                )
            if target.exists():
                if _sha256(target) == item["sha256"]:
                    reused += 1
                    continue
                conflicts.append(
                    {
                        "paper_uid": item["paper_uid"],
                        "target": target.relative_to(workspace).as_posix(),
                        "policy": "preserve-both",
                    }
                )
                target = target.with_name(
                    target.stem + f"-{str(feed['feed_id'])}" + target.suffix
                )
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary_target = target.with_name(target.name + ".tmp")
                shutil.copy2(source, temporary_target)
                temporary_target.replace(target)
            created += 1
        if not dry_run:
            paper_items = [
                item
                for item in manifests
                if "analysis_id" not in item
            ]
            if auto_download_pdf:
                for item in paper_items:
                    if _download_linked_pdf(workspace, item):
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
        }


def _download_linked_pdf(workspace: Path, item: dict[str, Any]) -> bool:
    pdf = item.get("pdf") or {}
    source_url = str(pdf.get("source_url") or "")
    if not source_url:
        return False
    paper_id = str(item.get("source_id") or item["paper_uid"]).replace(":", "_")
    target = workspace / "80 Attachments/Papers" / f"{paper_id}.pdf"
    if target.exists():
        if not target.read_bytes()[:5] == b"%PDF-":
            raise ValueError(f"Existing PDF has an invalid header: {target}")
        expected = str(pdf.get("expected_sha256") or "")
        if expected and _sha256(target) != expected:
            raise ValueError(f"Existing PDF checksum mismatch: {target}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    digest = hashlib.sha256()
    size = 0
    with httpx.stream(
        "GET", source_url, timeout=60, follow_redirects=True
    ) as response:
        response.raise_for_status()
        with temporary.open("wb") as output:
            for chunk in response.iter_bytes():
                digest.update(chunk)
                size += len(chunk)
                output.write(chunk)
    try:
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


def _render_local_note(
    workspace: Path,
    feed_root: Path,
    item: dict[str, Any],
    *,
    feed_id: str,
) -> Path:
    from paperflow.config import load_config
    from paperflow.obsidian.note_renderer import render_paper
    from paperflow.pipeline.import_paper import pending_analysis

    raw = json.loads(
        resolve_feed_file(feed_root, item["path"]).read_text(encoding="utf-8")
    )
    record = {**raw["metadata"], **pending_analysis()}
    record["paper_uid"] = raw["paper_uid"]
    analyses = [
        json.loads(line)
        for line in (feed_root / "manifests/analyses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and json.loads(line).get("paper_uid") == raw["paper_uid"]
    ]
    if analyses:
        selected = analyses[-1]
        analysis = json.loads(
            resolve_feed_file(feed_root, selected["path"]).read_text(
                encoding="utf-8"
            )
        )
        record.update(analysis["analysis"])
        record["system_selected_analysis_id"] = analysis["analysis_id"]
        record["system_selected_analysis_publisher"] = feed_id
        record["ai_analysis_provider"] = analysis["identity"].get(
            "provider", ""
        )
        record["ai_analysis_model"] = analysis["identity"].get("model", "")
        record["ai_analysis_prompt_version"] = analysis["identity"].get(
            "prompt_version", ""
        )
        record["ai_analyzed_at"] = analysis.get("created_at", "")
    cfg = load_config(workspace)
    paper_id = str(raw.get("source_id") or raw["paper_uid"]).replace(":", "_")
    year = record.get("paper_year") or str(
        record.get("paper_submitted_date") or ""
    )[:4]
    relative = Path(str(year or "Unclassified")) / f"{paper_id}.md"
    note = cfg.path("paper_folder") / relative
    pdf = workspace / "80 Attachments/Papers" / f"{paper_id}.pdf"
    record["paper_pdf_path"] = (
        pdf.relative_to(workspace).as_posix() if pdf.exists() else ""
    )
    record.setdefault("paper_title", paper_id)
    record.setdefault("paper_authors", [])
    record.setdefault("paper_first_author", "")
    for key in [
        "paper_arxiv_id",
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
