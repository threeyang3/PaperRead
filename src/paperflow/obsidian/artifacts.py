from __future__ import annotations

"""Independent Paper Workspace artifacts.

The main paper note remains the stable Paper Hub path.  AI analysis and user
prose are separate files so a public feed can never be changed by a local
reader edit, and re-rendering generated content cannot overwrite user prose.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from paperflow.paths.service import record_variables
from paperflow.paths.templates import SafePathTemplate, resolve_inside
from paperflow.utils import atomic_write, iso_beijing, now_beijing
from paperflow.obsidian.frontmatter import dump_frontmatter, read_note, write_note

USER_RE = re.compile(
    r"<!-- USER_NOTES_START -->(.*?)<!-- USER_NOTES_END -->", re.S
)
MIGRATION_MARKER = "paperflow-user-note-migrated"
MIGRATED_LINK_RE = re.compile(
    r"(?:已迁移到|migrated\s+to)\s+\[\[([^\]]+)\]\]",
    re.IGNORECASE,
)


def has_external_user_note(root: Path, record: dict[str, Any], body: str) -> bool:
    """Return whether a Hub safely points at its independent User Note.

    Older migrations wrote the link but predated the durable marker.  Accept
    those links only when the target is inside the Vault, has the expected
    artifact type, and belongs to the same paper UID.
    """
    if MIGRATION_MARKER in body:
        return True
    uid = _uid(record)
    if not uid:
        return False
    root_resolved = root.resolve()
    for value in MIGRATED_LINK_RE.findall(body):
        relative = value.strip()
        candidate = root / relative
        if candidate.suffix.casefold() != ".md":
            candidate = Path(str(candidate) + ".md")
        try:
            candidate = candidate.resolve()
            candidate.relative_to(root_resolved)
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        try:
            frontmatter, _ = read_note(candidate)
        except Exception:
            continue
        if (
            frontmatter.get("type") == "paper-user-note"
            and str(frontmatter.get("paper_uid") or "") == uid
        ):
            return True
    return False


def artifact_path(root: Path, settings: Any, record: dict[str, Any], name: str) -> Path:
    rule = getattr(settings.paths, name)
    relative = SafePathTemplate(
        rule.template,
        missing_value=settings.path_templates.missing_value,
        max_path_length=settings.path_templates.max_path_length,
    ).render(record_variables(record, profile=settings.ai.full_analysis_profile))
    return resolve_inside(root / rule.root, relative)


def _uid(record: dict[str, Any]) -> str:
    return str(record.get("paper_uid") or record.get("paper_arxiv_id") or "")


def ensure_user_note(
    root: Path,
    settings: Any,
    record: dict[str, Any],
    *,
    content: str = "",
    locale: str = "zh-CN",
) -> dict[str, Any]:
    path = artifact_path(root, settings, record, "user_note")
    if path.exists():
        return {
            "path": path.relative_to(root).as_posix(),
            "created": False,
            "status": "existing",
        }
    title = str(record.get("paper_display_title") or record.get("paper_title_display") or record.get("paper_title") or _uid(record))
    body = content.strip()
    if not body:
        body = (
            "# 我的笔记\n\n"
            "## 观察\n\n"
            "## 疑问\n\n"
            "## 可借鉴思路\n\n"
            "## 后续行动\n"
        ) if locale != "en" else (
            "# My notes\n\n## Observations\n\n## Questions\n\n"
            "## Ideas to reuse\n\n## Next actions\n"
        )
    values = {
        "type": "paper-user-note",
        "schema_version": 1,
        "paper_uid": _uid(record),
        "paper_id": record.get("paper_arxiv_id", ""),
        "title": f"我的笔记 · {title}" if locale != "en" else f"My notes · {title}",
        "aliases": [f"User notes {record.get('paper_arxiv_id', '')}"],
        "paper_hub": record.get("note_path", ""),
        "created_at": iso_beijing(),
        "updated_at": iso_beijing(),
        "system_managed": False,
    }
    write_note(path, values, body)
    return {
        "path": path.relative_to(root).as_posix(),
        "created": True,
        "status": "created",
    }


def ensure_ai_analysis_note(
    root: Path,
    settings: Any,
    record: dict[str, Any],
    body: str,
    *,
    locale: str = "zh-CN",
) -> dict[str, Any]:
    path = artifact_path(root, settings, record, "ai_analysis_note")
    generated = USER_RE.sub("", body).strip() + "\n"
    title = str(record.get("paper_display_title") or record.get("paper_title_display") or record.get("paper_title") or _uid(record))
    values = {
        "type": "paper-ai-analysis",
        "schema_version": 1,
        "paper_uid": _uid(record),
        "paper_id": record.get("paper_arxiv_id", ""),
        "title": f"AI 分析 · {title}" if locale != "en" else f"AI analysis · {title}",
        "aliases": [f"AI analysis {record.get('paper_arxiv_id', '')}"],
        "paper_hub": record.get("note_path", ""),
        "analysis_prompt_version": record.get("ai_analysis_prompt_version", ""),
        "analysis_content_hash": hashlib.sha256(generated.encode("utf-8")).hexdigest(),
        "updated_at": iso_beijing(),
        "system_generated": True,
    }
    # AI artifacts are generated snapshots; never merge user prose into them.
    write_note(path, values, generated)
    return {"path": path.relative_to(root).as_posix(), "status": "written"}


def hub_links(root: Path, settings: Any, record: dict[str, Any]) -> dict[str, str]:
    def rel(path: Path) -> str:
        return path.relative_to(root).as_posix()

    result = {
        "paper_hub": str(record.get("note_path") or ""),
        "ai_analysis": rel(artifact_path(root, settings, record, "ai_analysis_note")),
        "user_note": rel(artifact_path(root, settings, record, "user_note")),
    }
    for name, key in (("annotation_note", "annotations"), ("paper_review", "review"), ("community_note", "community"), ("pdf", "pdf")):
        try:
            result[key] = rel(artifact_path(root, settings, record, name))
        except Exception:
            result[key] = ""
    return result


def _record_for_note(root: Path, note: Path) -> dict[str, Any]:
    frontmatter, _ = read_note(note)
    if frontmatter.get("paper_uid"):
        return frontmatter
    paper_id = note.stem.replace(".md", "")
    for candidate in (root / ".paperflow/data/papers").glob("*.json"):
        value = json.loads(candidate.read_text(encoding="utf-8"))
        if str(value.get("paper_arxiv_id") or value.get("paper_uid", "")).replace(":", "_") == paper_id:
            return value
    return {"paper_uid": f"arxiv:{paper_id}", "paper_arxiv_id": paper_id, "paper_title": paper_id, "note_path": note.relative_to(root).as_posix()}


def plan_user_note_migration(root: Path, settings: Any) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for note in sorted((root / settings.paths.note.root).rglob("*.md")):
        frontmatter, body = read_note(note)
        match = USER_RE.search(body)
        if not match:
            continue
        content = match.group(1).strip()
        record = _record_for_note(root, note)
        record["note_path"] = note.relative_to(root).as_posix()
        if note.parent.name.isdigit() and len(note.parent.name) == 4:
            record.setdefault("paper_year", note.parent.name)
        target = artifact_path(root, settings, record, "user_note")
        items.append({
            "source": note.relative_to(root).as_posix(),
            "target": target.relative_to(root).as_posix(),
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content_empty": not bool(content),
            "target_exists": target.exists(),
            "paper_uid": _uid(record),
        })
    return {"dry_run": True, "items": items, "count": len(items)}


def apply_user_note_migration(root: Path, settings: Any) -> dict[str, Any]:
    plan = plan_user_note_migration(root, settings)
    backup_root = root / ".paperflow/backups" / f"user-notes-{now_beijing().strftime('%Y%m%d-%H%M%S')}"
    changed = 0
    conflicts: list[dict[str, Any]] = []
    for item in plan["items"]:
        source = root / item["source"]
        target = root / item["target"]
        frontmatter, body = read_note(source)
        match = USER_RE.search(body)
        if not match:
            continue
        record = dict(frontmatter)
        record["note_path"] = item["source"]
        source_year = source.parent.name
        if source_year.isdigit() and len(source_year) == 4:
            record.setdefault("paper_year", source_year)
        if target.exists():
            target_frontmatter, _ = read_note(target)
            if target_frontmatter.get("type") != "paper-user-note" or target_frontmatter.get("paper_uid") != _uid(record):
                conflicts.append({"source": item["source"], "target": item["target"], "reason": "target-exists"})
                continue
        backup = backup_root / source.relative_to(root)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(source.read_bytes())
        if not target.exists():
            ensure_user_note(root, settings, record, content=match.group(1), locale="en" if "my notes" in match.group(1).lower() else "zh-CN")
        link = f"\n## 用户笔记\n\n> 已迁移到 [[{target.relative_to(root).with_suffix('').as_posix()}]]。\n\n<!-- {MIGRATION_MARKER} source={item['source']} sha256={item['content_sha256']} -->\n"
        new_body = USER_RE.sub(link, body, count=1)
        atomic_write(source, dump_frontmatter(frontmatter) + "\n" + new_body.lstrip())
        changed += 1
    return {"dry_run": False, "items": plan["items"], "changed": changed, "conflicts": conflicts, "backup": backup_root.relative_to(root).as_posix() if changed else ""}
