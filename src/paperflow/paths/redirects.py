"""Make legacy paper-path redirect notes understandable in Obsidian."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paperflow.obsidian.frontmatter import dump_frontmatter, read_note
from paperflow.utils import atomic_write, iso_beijing, now_beijing


MIGRATION_ID = "paths-0002-readable-redirect-labels"
_LINK = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")


def _target_from_body(body: str) -> str | None:
    match = _LINK.search(body)
    if not match:
        return None
    return match.group(1).strip()


def _display_title(root: Path, target: str) -> str:
    path = root / (target if target.endswith(".md") else target + ".md")
    if path.exists():
        try:
            frontmatter, _ = read_note(path)
        except Exception:
            frontmatter = {}
        for key in ("paper_title_display", "paper_display_title", "title"):
            value = frontmatter.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return Path(target).stem


def _is_plain_generated_redirect(frontmatter: dict[str, Any], body: str) -> bool:
    if frontmatter.get("paperflow_redirect") is not True:
        return False
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return True
    target = _target_from_body(body)
    if not target:
        return False
    if len(lines) == 2 and lines[0].casefold() in {"# moved", "# 已移动"}:
        return True
    return lines == [
        "# 已迁移的论文笔记",
        "这是旧路径兼容入口，实际论文笔记已使用可读文件名。",
        f"→ [[{target}|打开论文笔记]]",
    ]


def _desired(frontmatter: dict[str, Any], target: str, title: str, old_stem: str) -> str:
    updated = dict(frontmatter)
    updated["type"] = "paper-redirect"
    updated["paperflow_redirect"] = True
    updated["redirect_target"] = target
    updated["title"] = f"兼容入口 · {title}"
    aliases = updated.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    updated["aliases"] = list(dict.fromkeys([old_stem, title, *(str(value) for value in aliases)]))
    return (
        dump_frontmatter(updated)
        + "\n"
        + f"# 已迁移：{title}\n\n"
        "这是旧路径兼容入口，实际论文笔记已使用可读文件名。\n\n"
        f"→ [[{target}|打开论文笔记]]\n"
    )


def plan_redirect_labels(root: Path) -> dict[str, Any]:
    """Plan labels for generated redirect notes without changing user content."""
    changes: list[dict[str, str]] = []
    manual_review: list[str] = []
    for path in sorted((root / "10 Papers").rglob("*.md")) if (root / "10 Papers").exists() else []:
        try:
            frontmatter, body = read_note(path)
        except Exception:
            continue
        if frontmatter.get("type") != "paper-redirect":
            continue
        target = _target_from_body(body) or str(frontmatter.get("redirect_target") or "")
        if not target:
            manual_review.append(path.relative_to(root).as_posix())
            continue
        if not _is_plain_generated_redirect(frontmatter, body) and not frontmatter.get("redirect_target"):
            manual_review.append(path.relative_to(root).as_posix())
            continue
        title = _display_title(root, target)
        desired = _desired(frontmatter, target, title, path.stem)
        if desired != path.read_text(encoding="utf-8"):
            changes.append({
                "path": path.relative_to(root).as_posix(),
                "target": target,
                "title": title,
            })
    return {
        "migration_id": MIGRATION_ID,
        "dry_run": True,
        "changes": changes,
        "count": len(changes),
        "manual_review": manual_review,
        "policy": "decorate generated redirect stubs; never overwrite user-authored redirect content",
    }


def apply_redirect_labels(root: Path) -> dict[str, Any]:
    plan = plan_redirect_labels(root)
    if not plan["changes"]:
        return {**plan, "dry_run": False, "status": "already-applied"}
    backup = root / ".paperflow/backups" / f"redirect-labels-{now_beijing().strftime('%Y%m%d-%H%M%S')}"
    changed: list[str] = []
    for item in plan["changes"]:
        path = root / item["path"]
        frontmatter, body = read_note(path)
        target = item["target"]
        title = item["title"]
        snapshot = backup / "files" / item["path"]
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(path.read_bytes())
        atomic_write(path, _desired(frontmatter, target, title, path.stem))
        changed.append(item["path"])
    result = {
        **plan,
        "dry_run": False,
        "status": "applied",
        "at": iso_beijing(),
        "backup": backup.relative_to(root).as_posix(),
        "changed": changed,
    }
    history = root / ".paperflow/state/migrations/history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result
