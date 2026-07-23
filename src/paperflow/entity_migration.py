"""Normalize generated Topic/Method/Dataset entity notes."""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from paperflow.obsidian.frontmatter import dump_frontmatter, read_note
from paperflow.paths.templates import safe_component
from paperflow.utils import atomic_write, iso_beijing, now_beijing


MIGRATION_ID = "entities-0001-normalize-generated-notes"
ENTITY_FOLDERS = {
    "topic": Path("20 Topics"),
    "method": Path("20 Topics/Methods"),
    "dataset": Path("20 Topics/Datasets"),
}
_HYPHENS = re.compile(r"[\u2010-\u2015\-]")
_SPACE = re.compile(r"\s+")


def entity_key(value: str) -> str:
    """Normalize punctuation/case used by AI labels and legacy filenames."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _HYPHENS.sub(" ", text.replace("_", " "))
    return _SPACE.sub(" ", text).strip().casefold()


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
    if not values:
        values.append(path.stem)
    return list(dict.fromkeys(values))


def _entity_type(frontmatter: dict[str, Any]) -> str:
    value = str(frontmatter.get("type") or "").strip().casefold()
    if value in ENTITY_FOLDERS:
        return value
    tags = frontmatter.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    for tag in tags:
        tag = str(tag)
        if tag.startswith("entity/") and tag.removeprefix("entity/") in ENTITY_FOLDERS:
            return tag.removeprefix("entity/")
    return ""


def _is_generated_body(body: str) -> bool:
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in {"## 相关论文", "## Related papers"}:
            continue
        lines.append(stripped)
    return not lines


def _canonical_path(root: Path, kind: str, label: str) -> Path:
    folder = root / ENTITY_FOLDERS[kind]
    return folder / f"{safe_component(label)[:100]}.md"


def _incoming_links(root: Path, path: Path) -> int:
    target = path.relative_to(root).with_suffix("").as_posix()
    count = 0
    for note in root.rglob("*.md"):
        relative = note.relative_to(root).as_posix()
        if relative.startswith(".paperflow/backups/"):
            continue
        try:
            text = note.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        count += text.count(f"[[{target}]]") + text.count(f"[[{target}|")
    return count


def _rewrite_links(root: Path, replacements: dict[str, str]) -> list[str]:
    changed: list[str] = []
    for note in sorted(root.rglob("*.md")):
        relative = note.relative_to(root).as_posix()
        if relative.startswith(".paperflow/backups/"):
            continue
        try:
            text = note.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(f"[[{old}]]", f"[[{new}]]")
            updated = updated.replace(f"[[{old}|", f"[[{new}|")
        if updated != text:
            atomic_write(note, updated)
            changed.append(relative)
    return changed


def _merge_entity(canonical: Path, duplicate: Path, kind: str) -> tuple[bool, str]:
    canonical_frontmatter, canonical_body = read_note(canonical)
    duplicate_frontmatter, duplicate_body = read_note(duplicate)
    canonical_labels = _labels(canonical_frontmatter, canonical)
    duplicate_labels = _labels(duplicate_frontmatter, duplicate)
    aliases = canonical_frontmatter.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    for value in [*duplicate_labels, *aliases]:
        value = str(value).strip()
        if value and value not in canonical_labels:
            canonical_labels.append(value)
    label = str(canonical_frontmatter.get("title") or canonical_labels[0]).strip()
    canonical_frontmatter.pop("topic_name", None)
    canonical_frontmatter.pop("method_name", None)
    canonical_frontmatter.pop("dataset_name", None)
    canonical_frontmatter["type"] = kind
    canonical_frontmatter["title"] = label
    canonical_frontmatter["aliases"] = canonical_labels
    tags = canonical_frontmatter.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(value) for value in tags]
    entity_tag = f"entity/{kind}"
    if entity_tag not in tags:
        tags.append(entity_tag)
    canonical_frontmatter["tags"] = tags
    extra = ""
    if not _is_generated_body(duplicate_body):
        extra = (
            "\n\n## 合并内容\n\n"
            f"> 来源：{duplicate.as_posix()}\n\n"
            + duplicate_body.strip()
        )
    body = canonical_body.rstrip()
    if extra and extra.strip() not in body:
        body += extra
    atomic_write(canonical, dump_frontmatter(canonical_frontmatter) + "\n" + body + "\n")
    return _is_generated_body(duplicate_body), label


def plan_entity_normalization(root: Path) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    for kind, folder in ENTITY_FOLDERS.items():
        directory = root / folder
        by_key: dict[str, list[Path]] = {}
        for path in sorted(directory.glob("*.md")) if directory.exists() else []:
            try:
                frontmatter, _ = read_note(path)
            except Exception:
                continue
            detected = _entity_type(frontmatter)
            if detected and detected != kind:
                continue
            labels = _labels(frontmatter, path)
            key = entity_key(labels[0])
            if key:
                by_key.setdefault(key, []).append(path)
        for key, files in sorted(by_key.items()):
            if len(files) < 2:
                continue
            labels = []
            for path in files:
                labels.extend(_labels(read_note(path)[0], path))
            label = next((value for value in labels if entity_key(value) == key), labels[0])
            target = _canonical_path(root, kind, label)
            canonical = next((path for path in files if path.name.casefold() == target.name.casefold()), None)
            if canonical is None:
                canonical = max(files, key=lambda path: (_incoming_links(root, path), path.name.casefold()))
            duplicates = [path for path in files if path != canonical]
            groups.append({
                "kind": kind,
                "key": key,
                "label": label,
                "canonical": canonical.relative_to(root).as_posix(),
                "duplicates": [path.relative_to(root).as_posix() for path in duplicates],
                "count": len(duplicates),
            })
    return {
        "migration_id": MIGRATION_ID,
        "dry_run": True,
        "groups": groups,
        "duplicate_count": sum(item["count"] for item in groups),
        "policy": (
            "one canonical slug per entity type; merge aliases; update wikilinks; "
            "backup and remove only empty generated duplicates"
        ),
    }


def apply_entity_normalization(root: Path) -> dict[str, Any]:
    plan = plan_entity_normalization(root)
    if not plan["groups"]:
        return {**plan, "dry_run": False, "status": "already-applied"}
    backup = root / ".paperflow/backups" / f"entities-{now_beijing().strftime('%Y%m%d-%H%M%S')}"
    replacements: dict[str, str] = {}
    merged: list[str] = []
    kept_for_review: list[str] = []
    for group in plan["groups"]:
        canonical = root / group["canonical"]
        canonical.parent.mkdir(parents=True, exist_ok=True)
        for relative in group["duplicates"]:
            duplicate = root / relative
            if not duplicate.exists():
                continue
            target = canonical.relative_to(root).with_suffix("").as_posix()
            old = duplicate.relative_to(root).with_suffix("").as_posix()
            replacements[old] = target
            snapshot = backup / "files" / relative
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(duplicate, snapshot)
            removable, _ = _merge_entity(canonical, duplicate, group["kind"])
            if removable:
                duplicate.unlink()
                merged.append(relative)
            else:
                kept_for_review.append(relative)
    changed_links = _rewrite_links(root, replacements)
    result = {
        **plan,
        "dry_run": False,
        "status": "applied",
        "at": iso_beijing(),
        "backup": backup.relative_to(root).as_posix(),
        "merged": merged,
        "kept_for_review": kept_for_review,
        "changed_links": changed_links,
    }
    history = root / ".paperflow/state/migrations/history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    return result
