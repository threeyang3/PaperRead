from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperflow.utils import atomic_json
from paperflow.zotero.store import data_root


INDEX_SCHEMA_VERSION = 1


def mapping_root(root: Path) -> Path:
    return data_root(root) / "connectors/zotero/mappings"


def index_path(root: Path) -> Path:
    return data_root(root) / "connectors/zotero/mapping-index.json"


def _build_mapping_index(root: Path) -> dict[str, Any]:
    by_item_key: dict[str, str] = {}
    by_paper_uid: dict[str, str] = {}
    directory = mapping_root(root)
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        paper_uid = str(value.get("paper_uid") or "").strip()
        item_key = str((value.get("zotero") or {}).get("item_key") or "").strip()
        if paper_uid:
            if paper_uid in by_paper_uid and by_paper_uid[paper_uid] != path.name:
                raise ValueError(
                    f"duplicate Zotero mapping for paper_uid {paper_uid}: "
                    f"{by_paper_uid[paper_uid]}, {path.name}"
                )
            by_paper_uid[paper_uid] = path.name
        if item_key:
            if item_key in by_item_key and by_item_key[item_key] != path.name:
                raise ValueError(
                    f"duplicate Zotero mapping for item_key {item_key}: "
                    f"{by_item_key[item_key]}, {path.name}"
                )
            by_item_key[item_key] = path.name
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "by_item_key": dict(sorted(by_item_key.items())),
        "by_paper_uid": dict(sorted(by_paper_uid.items())),
    }


def rebuild_mapping_index(root: Path) -> dict[str, Any]:
    value = _build_mapping_index(root)
    atomic_json(index_path(root), value)
    return value


def _load_index(root: Path) -> dict[str, Any]:
    try:
        value = json.loads(index_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return rebuild_mapping_index(root)
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != INDEX_SCHEMA_VERSION
        or not isinstance(value.get("by_item_key"), dict)
        or not isinstance(value.get("by_paper_uid"), dict)
    ):
        return rebuild_mapping_index(root)
    return value


def _mapping_from_name(root: Path, name: object) -> dict[str, Any] | None:
    filename = str(name or "")
    if not filename or Path(filename).name != filename or not filename.endswith(".json"):
        return None
    try:
        value = json.loads((mapping_root(root) / filename).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def mapping_for_item(root: Path, item_key: str) -> dict[str, Any] | None:
    index = _load_index(root)
    value = _mapping_from_name(root, index["by_item_key"].get(item_key))
    if value is not None and (value.get("zotero") or {}).get("item_key") == item_key:
        return value
    index = rebuild_mapping_index(root)
    return _mapping_from_name(root, index["by_item_key"].get(item_key))


def mapping_for_paper(root: Path, paper_uid: str) -> dict[str, Any] | None:
    index = _load_index(root)
    value = _mapping_from_name(root, index["by_paper_uid"].get(paper_uid))
    if value is not None and value.get("paper_uid") == paper_uid:
        return value
    index = rebuild_mapping_index(root)
    return _mapping_from_name(root, index["by_paper_uid"].get(paper_uid))


def diagnose_mapping_index(root: Path) -> dict[str, Any]:
    try:
        rebuilt = _build_mapping_index(root)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    target = index_path(root)
    if not target.exists() and not rebuilt["by_paper_uid"]:
        return {"ok": True, "mappings": 0, "items": 0, "status": "not-needed"}
    try:
        current = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": current == rebuilt,
        "mappings": len(rebuilt["by_paper_uid"]),
        "items": len(rebuilt["by_item_key"]),
    }


__all__ = [
    "index_path",
    "mapping_for_item",
    "mapping_for_paper",
    "diagnose_mapping_index",
    "mapping_root",
    "rebuild_mapping_index",
]
