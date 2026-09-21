from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from paperflow.data.records import UserPaperRecord
from paperflow.paths.templates import safe_component
from paperflow.workspace import dump_yaml


def user_sidecar_path(root: Path, record: dict[str, Any]) -> Path:
    paper_id = str(record.get("paper_arxiv_id") or record.get("paper_uid") or "unknown").replace(
        ":", "_"
    )
    return root / ".paperflow/data/user" / f"{safe_component(paper_id)}.yaml"


def load_user_record(root: Path, record: dict[str, Any]) -> UserPaperRecord | None:
    path = user_sidecar_path(root, record)
    if not path.exists():
        return None
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    return UserPaperRecord.model_validate(value)


def merge_user_data(
    root: Path,
    record: dict[str, Any],
    note_frontmatter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge legacy, sidecar, and Markdown projections without losing user data.

    Existing note properties have the highest priority because they are the
    direct user-editable Obsidian projection. Tags are merged as a set.
    """
    merged = {key: value for key, value in record.items() if key.startswith("user_")}
    sidecar = load_user_record(root, record)
    if sidecar:
        merged.update(sidecar.user)
    note_values = {
        key: value for key, value in (note_frontmatter or {}).items() if key.startswith("user_")
    }
    old_tags = list(merged.get("user_added_tags") or [])
    note_tags = list(note_values.get("user_added_tags") or [])
    merged.update(note_values)
    merged["user_added_tags"] = list(dict.fromkeys([*old_tags, *note_tags]))
    return merged


def save_user_record(
    root: Path,
    record: dict[str, Any],
    user_values: dict[str, Any],
) -> Path:
    path = user_sidecar_path(root, record)
    sidecar = UserPaperRecord(
        paper_uid=str(record["paper_uid"]),
        user={key: value for key, value in user_values.items() if key.startswith("user_")},
    )
    dump_yaml(path, sidecar.model_dump(mode="json"))
    return path


def merge_user_values(
    current: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Apply explicit user updates while preserving unrelated fields and tags."""
    merged = {key: value for key, value in current.items() if key.startswith("user_")}
    existing_tags = list(merged.get("user_added_tags") or [])
    incoming_tags = list(updates.get("user_added_tags") or [])
    merged.update(
        {
            key: value
            for key, value in updates.items()
            if key.startswith("user_") and key != "user_added_tags"
        }
    )
    if "user_added_tags" in updates:
        merged["user_added_tags"] = list(dict.fromkeys([*existing_tags, *incoming_tags]))
    return merged


def merge_and_save_user_record(
    root: Path,
    record: dict[str, Any],
    updates: dict[str, Any],
) -> Path:
    """Persist explicit user input without resetting existing user fields."""
    merged = merge_user_values(merge_user_data(root, record), updates)
    return save_user_record(root, record, merged)
