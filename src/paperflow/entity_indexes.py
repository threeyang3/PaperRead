"""Rebuild readable reverse indexes for Topic/Method/Dataset notes.

Entity notes are projections, not a second source of truth.  Paper records in
``.paperflow/data/papers`` remain canonical; this module only updates the
machine-managed list of papers inside each entity note and preserves any
user-authored prose outside that list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperflow.entity_migration import ENTITY_FOLDERS, entity_key
from paperflow.obsidian.frontmatter import dump_frontmatter, read_note
from paperflow.paths.templates import safe_component
from paperflow.text_quality import display_title
from paperflow.utils import atomic_write, iso_beijing, now_beijing


INDEX_START = "<!-- PAPERFLOW_ENTITY_INDEX_START -->"
INDEX_END = "<!-- PAPERFLOW_ENTITY_INDEX_END -->"
ENTITY_LABELS = {
    "topic": ("主题", "研究方向"),
    "method": ("方法", "可复用算法/训练/控制方法"),
    "dataset": ("数据集", "数据资源或评测基准"),
}


def _labels(record: dict[str, Any], kind: str) -> list[str]:
    key = {"topic": "ai_topics", "method": "ai_method_family", "dataset": "ai_datasets"}[kind]
    values = record.get(key) or []
    if isinstance(values, str):
        values = [values]
    return [" ".join(str(value).split()).strip() for value in values if str(value).strip()]


def _records(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted((root / ".paperflow/data/papers").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("paper_uid"):
            result.append(value)
    return result


def _paper_link(root: Path, record: dict[str, Any]) -> tuple[str, str] | None:
    note = str(record.get("note_path") or "").strip()
    if not note:
        return None
    target = root / note
    if not target.exists():
        return None
    title = str(
        record.get("paper_display_title")
        or record.get("paper_title_display")
        or record.get("paper_title")
        or record.get("paper_arxiv_id")
        or record.get("paper_uid")
        or "未命名论文"
    ).strip()
    return note.removesuffix(".md"), display_title(title)


def _candidate_path(root: Path, kind: str, label: str) -> Path:
    folder = root / ENTITY_FOLDERS[kind]
    desired = folder / f"{safe_component(label)[:100]}.md"
    if desired.exists():
        return desired
    wanted = entity_key(label)
    for path in sorted(folder.glob("*.md")) if folder.exists() else []:
        try:
            frontmatter, _ = read_note(path)
        except Exception:
            continue
        tags = frontmatter.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        detected = str(frontmatter.get("type") or "").casefold()
        if detected and detected != kind and f"entity/{kind}" not in tags:
            continue
        current = str(frontmatter.get("title") or path.stem)
        if entity_key(current) == wanted:
            return path
    return desired


def _generated_block(items: list[tuple[str, str]]) -> str:
    lines = [INDEX_START]
    if items:
        lines.extend(f"- [[{path}|{title}]]" for path, title in items)
    else:
        lines.append("- 暂无已导入论文")
    lines.append(INDEX_END)
    return "\n".join(lines)


def _replace_index(body: str, items: list[tuple[str, str]]) -> str:
    block = _generated_block(items)
    if INDEX_START in body and INDEX_END in body:
        before, rest = body.split(INDEX_START, 1)
        _, after = rest.split(INDEX_END, 1)
        return before.rstrip() + "\n\n" + block + after
    heading = "## 相关论文"
    if heading in body:
        before, after = body.split(heading, 1)
        # Keep an existing user section after the generated list intact.
        return before.rstrip() + "\n\n" + heading + "\n\n" + block + after
    return body.rstrip() + "\n\n" + heading + "\n\n" + block + "\n"


def _render_entity(
    root: Path,
    kind: str,
    label: str,
    items: list[tuple[str, str]],
    *,
    apply: bool,
    backup_root: Path | None,
) -> dict[str, Any]:
    path = _candidate_path(root, kind, label)
    display = str(label).strip()
    kind_label, scope = ENTITY_LABELS[kind]
    if path.exists():
        frontmatter, body = read_note(path)
        detected = str(frontmatter.get("type") or "").casefold()
        tags = frontmatter.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        if detected and detected != kind and f"entity/{kind}" not in tags:
            return {
                "kind": kind,
                "label": display,
                "path": path.relative_to(root).as_posix(),
                "status": "manual-review",
                "reason": "existing note has a different entity type",
            }
    else:
        frontmatter = {
            "type": kind,
            "title": display,
            "tags": [f"entity/{kind}"],
            "aliases": [display],
        }
        body = f"# {display}\n\n"
    frontmatter["type"] = kind
    frontmatter["title"] = str(frontmatter.get("title") or display)
    aliases = frontmatter.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    frontmatter["aliases"] = list(dict.fromkeys([display, *(str(value) for value in aliases)]))
    if f"entity/{kind}" not in [str(value) for value in (frontmatter.get("tags") or [])]:
        tags = frontmatter.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        frontmatter["tags"] = [*tags, f"entity/{kind}"]
    intro = (
        f"> 实体类型：{kind_label} · {scope}\n"
        f"> 规范键：`{entity_key(display)}` · 已关联论文：{len(items)}\n"
    )
    lines = body.splitlines()
    metadata_lines = [line for line in lines if line.startswith("> 实体类型：") or line.startswith("> 规范键：")]
    if metadata_lines:
        normalized: list[str] = []
        inserted = False
        for line in lines:
            if line.startswith("> 实体类型：") or line.startswith("> 规范键："):
                if not inserted:
                    normalized.extend(intro.rstrip().splitlines())
                    inserted = True
                continue
            normalized.append(line)
        body = "\n".join(normalized)
    else:
        heading_index = next(
            (index for index, line in enumerate(lines) if line.startswith("# ") and not line.startswith("## ")),
            -1,
        )
        if heading_index >= 0:
            lines[heading_index + 1 : heading_index + 1] = ["", intro.rstrip()]
            body = "\n".join(lines)
        else:
            body = intro + "\n" + body.lstrip()
    updated = dump_frontmatter(frontmatter) + "\n" + _replace_index(body, items).rstrip() + "\n"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    changed = current != updated
    if apply and changed:
        if backup_root is not None and path.exists():
            snapshot = backup_root / "files" / path.relative_to(root)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(path.read_bytes())
        atomic_write(path, updated)
    return {
        "kind": kind,
        "label": display,
        "path": path.relative_to(root).as_posix(),
        "paper_count": len(items),
        "changed": changed,
        "status": "updated" if apply and changed else "planned" if changed else "unchanged",
    }


def rebuild_entity_indexes(
    root: Path,
    *,
    apply: bool = False,
    backup: bool = True,
    record_history: bool = True,
) -> dict[str, Any]:
    """Plan or apply reverse indexes while preserving user-authored sections."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in _records(root):
        link = _paper_link(root, record)
        if link is None:
            continue
        for kind in ENTITY_FOLDERS:
            for label in _labels(record, kind):
                key = (kind, entity_key(label))
                entry = grouped.setdefault(key, {"kind": kind, "label": label, "items": {}})
                entry["items"][link[0]] = link[1]
    backup_root = None
    if apply and backup:
        backup_root = root / ".paperflow/backups" / f"entity-index-{now_beijing().strftime('%Y%m%d-%H%M%S')}"
    changes: list[dict[str, Any]] = []
    for entry in sorted(grouped.values(), key=lambda item: (item["kind"], entity_key(item["label"]))):
        items = sorted(entry["items"].items(), key=lambda item: item[1].casefold())
        changes.append(_render_entity(root, entry["kind"], entry["label"], items, apply=apply, backup_root=backup_root))
    result = {
        "migration_id": "entities-0003-reverse-index",
        "dry_run": not apply,
        "status": "applied" if apply else "planned",
        "entity_count": len(changes),
        "changed_count": sum(bool(item.get("changed")) for item in changes),
        "manual_review": [item for item in changes if item.get("status") == "manual-review"],
        "changes": changes,
    }
    if apply:
        result["at"] = iso_beijing()
        result["backup"] = backup_root.relative_to(root).as_posix() if backup_root else ""
        if record_history:
            history = root / ".paperflow/state/migrations/history.jsonl"
            history.parent.mkdir(parents=True, exist_ok=True)
            with history.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    return result
