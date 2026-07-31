"""Reader-focused AI Markdown projection for Zotero attachments.

The projection is a system-managed view of AI Raw data.  It deliberately keeps
metadata in frontmatter, omits repeated author/URL paragraphs, and refuses to
overwrite a user-edited projection unless a caller explicitly chooses a new
output path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperflow.obsidian.frontmatter import dump_frontmatter
from paperflow.utils import atomic_json, atomic_write, iso_beijing
from paperflow.zotero.store import data_root, standalone
from paperflow.security.artifacts import PermissionGuard


def _text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _authors(record: dict[str, Any]) -> list[str]:
    values = record.get("paper_authors") or record.get("authors") or []
    if isinstance(values, str):
        values = [values]
    names = [_text(value.get("name") if isinstance(value, dict) else value) for value in values]
    names = [value for value in names if value]
    return names[:2] + (["et al."] if len(names) > 2 else [])


def _field(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _list(record: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = record.get(key)
        if isinstance(value, list):
            return [_text(item) for item in value if _text(item)]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _paper_record(root: Path, paper_uid: str) -> dict[str, Any]:
    safe = paper_uid.replace(":", "_")
    candidates = [root / ".paperflow/data/papers" / f"{safe}.json", data_root(root) / "papers" / f"{safe}.json"]
    for path in candidates:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                # A standalone Core keeps the bibliographic paper record and
                # append-only AI Raw separate.  Merge only the selected AI
                # payload into this read model; never rewrite the source file.
                if (root / "data").is_dir() and not (root / ".paperflow").exists():
                    from paperflow.zotero.standalone_ai import load_current_analysis

                    selected = load_current_analysis(root, paper_uid)
                    if isinstance(selected, dict) and isinstance(selected.get("analysis"), dict):
                        value = {
                            **value,
                            **selected["analysis"],
                            "ai_analysis_provider": (selected.get("identity") or {}).get("provider", ""),
                            "ai_analysis_model": (selected.get("identity") or {}).get("model", ""),
                            "ai_analysis_profile": (selected.get("identity") or {}).get("profile", ""),
                            "ai_analyzed_at": selected.get("analyzed_at", ""),
                        }
                return value
    raise FileNotFoundError(f"paper record not found: {paper_uid}")


def _projection_path(root: Path, paper_uid: str, target: str = "zotero") -> Path:
    safe = paper_uid.replace(":", "_")
    if target == "obsidian":
        return root / "20 AI Analyses" / f"{safe}.analysis.md"
    if standalone(root):
        return root / "documents/zotero" / f"{safe}.analysis.md"
    return root / ".paperflow/data/zotero/markdown" / f"{safe}.analysis.md"


def _render_state_path(root: Path, paper_uid: str) -> Path:
    return data_root(root) / "derived/ai-render-state" / f"{paper_uid.replace(':', '_')}.json"


def build_ai_markdown(record: dict[str, Any], *, zotero_item_key: str = "") -> str:
    title = _field(record, "paper_title_display", "paper_display_title", "paper_title") or "Untitled"
    summary = _field(record, "ai_summary_short", "ai_one_sentence_summary")
    contributions = _list(record, "ai_contributions", "ai_key_contributions", "ai_novelty_points")
    methods = _list(record, "ai_method_family", "ai_methods")
    evidence = _list(record, "ai_experimental_findings", "ai_results", "ai_evidence")
    limitations = _list(record, "ai_limitations", "ai_risks", "ai_open_questions")
    questions = _list(record, "ai_feynman_questions", "feynman_questions")
    if not summary:
        summary = "（当前分析没有提供一句话摘要。）"
    frontmatter = {
        "type": "paper-ai-analysis",
        "schema_version": 2,
        "artifact_permission": "USER_EDITABLE_PROJECTION",
        "paper_uid": _field(record, "paper_uid"),
        "title": title,
        "authors": _authors(record),
        "published_at": _field(record, "paper_submitted_date", "paper_published_date", "paper_year"),
        "venue": _field(record, "paper_published_venue") or "arXiv",
        "url": _field(record, "paper_abs_url", "paper_pdf_url"),
        "zotero_item_key": zotero_item_key,
        "analysis_status": _field(record, "ai_analysis_status") or "complete",
        "reading_status": _field(record, "user_reading_status") or "inbox",
        "review_status": _field(record, "user_review_status") or "pending",
        "reproduction_status": _field(record, "user_reproduction_status") or "not_started",
        # Keep the projection content-stable between renders.  A wall-clock
        # timestamp here would make an unchanged AI Raw look user-modified.
        "updated_at": _field(record, "ai_analyzed_at", "system_last_synced_at"),
    }
    sections = [f"# {title}", "", "## 一句话概述", "", summary]
    if contributions:
        sections += ["", "## 主要贡献", "", *[f"- {value}" for value in contributions]]
    if methods:
        sections += ["", "## 方法线索", "", *[f"- {value}" for value in methods]]
    if evidence:
        sections += ["", "## 证据与结果", "", *[f"- {value}" for value in evidence]]
    if limitations:
        sections += ["", "## 局限与风险", "", *[f"- {value}" for value in limitations]]
    if questions:
        sections += ["", "## 费曼问题", "", *[f"- [ ] {value}" for value in questions]]
    sections += ["", "---", "", "> 本页是 AI Raw 的系统管理投影；个人答案、复盘和复现记录请写入独立用户文档。", ""]
    return dump_frontmatter(frontmatter) + "\n" + "\n".join(sections)


def render_ai_projection(
    root: Path,
    paper_uid: str,
    *,
    zotero_item_key: str = "",
    output: Path | None = None,
    apply_changes: bool = False,
    target: str = "zotero",
) -> dict[str, Any]:
    if target not in {"zotero", "obsidian", "both"}:
        raise ValueError("target must be zotero, obsidian, or both")
    record = _paper_record(root, paper_uid)
    body = build_ai_markdown(record, zotero_item_key=zotero_item_key)
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    targets = [output.expanduser().resolve()] if output else [
        _projection_path(root, paper_uid, "zotero" if target == "both" else target)
    ]
    if target == "both" and output is None:
        targets = [_projection_path(root, paper_uid, "zotero"), _projection_path(root, paper_uid, "obsidian")]
    existing_by_path = {
        path: path.read_text(encoding="utf-8") if path.is_file() else ""
        for path in targets
    }
    changed_paths = [path for path, existing in existing_by_path.items() if existing != body]
    result: dict[str, Any] = {
        "paper_uid": paper_uid,
        "paths": [path.as_posix() for path in targets],
        "path": targets[0].as_posix(),
        "target": target,
        "dry_run": not apply_changes,
        "changed": bool(changed_paths),
        "content_sha256": content_hash,
        "permission": "USER_EDITABLE_PROJECTION",
    }
    if apply_changes:
        guard = PermissionGuard(root)
        modified = [path for path, existing in existing_by_path.items() if existing and existing != body]
        if modified:
            result.update({
                "status": "manual-review-required",
                "reason": "existing projection differs",
                "conflicts": [path.as_posix() for path in modified],
            })
            return result
        for path in targets:
            # The Markdown file is a user-editable projection: Core may create
            # it initially, but a later render must stop when a user changed
            # the existing bytes.  The explicit permission keeps this target
            # distinct from immutable Raw/AI records.
            guard.authorize(path, "USER_EDITABLE_PROJECTION")
            atomic_write(path, body)
        state_path = _render_state_path(root, paper_uid)
        guard.authorize(state_path, "SYSTEM_MANAGED")
        atomic_json(state_path, {
            "schema_version": 1,
            "paper_uid": paper_uid,
            "primary_target": target,
            "content_sha256": content_hash,
            "targets": {path.as_posix(): content_hash for path in targets},
            "artifact_permission": "SYSTEM_MANAGED",
            "updated_at": iso_beijing(),
        })
        result["render_state"] = state_path.as_posix()
        result["status"] = "written"
    else:
        result["status"] = "would-write" if changed_paths else "up-to-date"
    return result


__all__ = ["build_ai_markdown", "render_ai_projection"]
