"""Normalize display labels of generated entity notes without changing identity."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paperflow.entity_migration import ENTITY_FOLDERS, entity_key
from paperflow.obsidian.frontmatter import dump_frontmatter, read_note
from paperflow.utils import atomic_write, iso_beijing, now_beijing


MIGRATION_ID = "entities-0002-display-labels"


def _labels(frontmatter: dict[str, Any], path: Path) -> list[str]:
    values: list[str] = []
    for key in ("title", "topic_name", "method_name", "dataset_name"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    aliases = frontmatter.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    values.extend(str(value).strip() for value in aliases if str(value).strip())
    return list(dict.fromkeys(values or [path.stem]))


def _score(value: str) -> tuple[int, int, int, int]:
    """Prefer reader-friendly labels over AI slug/case variants."""
    return (
        int(value != value.casefold()),
        int(" " in value),
        int(not re.search(r"[-_]+", value)),
        -len(value),
    )


def _preferred_labels(root: Path) -> dict[str, str]:
    candidates: dict[str, list[str]] = {}
    for folder in ENTITY_FOLDERS.values():
        directory = root / folder
        for path in sorted(directory.glob("*.md")) if directory.exists() else []:
            try:
                frontmatter, _ = read_note(path)
            except Exception:
                continue
            for value in _labels(frontmatter, path):
                candidates.setdefault(entity_key(value), []).append(value)
    return {
        key: max(dict.fromkeys(values), key=_score)
        for key, values in candidates.items()
    }


def plan_entity_display_labels(root: Path) -> dict[str, Any]:
    preferred = _preferred_labels(root)
    changes: list[dict[str, str]] = []
    for kind, folder in ENTITY_FOLDERS.items():
        directory = root / folder
        for path in sorted(directory.glob("*.md")) if directory.exists() else []:
            try:
                frontmatter, body = read_note(path)
            except Exception:
                continue
            labels = _labels(frontmatter, path)
            current = str(frontmatter.get("title") or labels[0])
            desired = preferred.get(entity_key(current), current)
            if desired == current:
                continue
            changes.append(
                {
                    "kind": kind,
                    "path": path.relative_to(root).as_posix(),
                    "from": current,
                    "to": desired,
                }
            )
    return {
        "migration_id": MIGRATION_ID,
        "dry_run": True,
        "changes": changes,
        "count": len(changes),
        "policy": "preserve paths and bodies; normalize generated display labels and aliases only",
    }


def apply_entity_display_labels(root: Path) -> dict[str, Any]:
    plan = plan_entity_display_labels(root)
    if not plan["changes"]:
        return {**plan, "dry_run": False, "status": "already-applied"}
    backup = root / ".paperflow/backups" / f"entity-labels-{now_beijing().strftime('%Y%m%d-%H%M%S')}"
    changed: list[str] = []
    for item in plan["changes"]:
        path = root / item["path"]
        frontmatter, body = read_note(path)
        old = str(item["from"])
        new = str(item["to"])
        aliases = frontmatter.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        frontmatter["title"] = new
        frontmatter["aliases"] = list(dict.fromkeys([new, old, *(str(v) for v in aliases)]))
        lines = body.splitlines()
        for index, line in enumerate(lines):
            if line.strip() == f"# {old}":
                lines[index] = f"# {new}"
                break
        backup_path = backup / "files" / item["path"]
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(path.read_bytes())
        atomic_write(path, dump_frontmatter(frontmatter) + "\n" + "\n".join(lines).rstrip() + "\n")
        changed.append(item["path"])
    result = {**plan, "dry_run": False, "status": "applied", "at": iso_beijing(), "backup": backup.relative_to(root).as_posix(), "changed": changed}
    history = root / ".paperflow/state/migrations/history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result

