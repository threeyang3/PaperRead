from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperflow.sync_safety import find_sync_conflicts
from paperflow.text_quality import suspicious_text


def scan_workspace_health(root: Path) -> dict[str, Any]:
    mojibake: list[str] = []
    missing_visual_embeds: list[str] = []
    broken_assets: list[str] = []
    pending_reanalysis: list[str] = []
    for path in (root / ".paperflow/data/papers").glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mojibake.append(path.relative_to(root).as_posix())
            continue
        searchable = json.dumps(record, ensure_ascii=False)
        if suspicious_text(searchable):
            mojibake.append(path.relative_to(root).as_posix())
            if record.get("ai_analysis_status") == "complete":
                pending_reanalysis.append(str(record.get("paper_uid") or path.stem))
        assets = (record.get("extraction") or {}).get("visual_assets") or []
        note_path = root / str(record.get("note_path") or "")
        note_text = (
            note_path.read_text(encoding="utf-8") if note_path.is_file() else ""
        )
        if assets and not any(f"![[{item.get('path')}" in note_text for item in assets):
            missing_visual_embeds.append(str(record.get("paper_uid") or path.stem))
        for asset in assets:
            candidate = root / str(asset.get("path") or "")
            if not candidate.is_file():
                broken_assets.append(candidate.relative_to(root).as_posix())
    conflicts = [
        path.relative_to(root).as_posix() for path in find_sync_conflicts(root)
    ]
    return {
        "ok": not (mojibake or broken_assets or conflicts),
        "mojibake": mojibake,
        "missing_visual_embeds": missing_visual_embeds,
        "broken_assets": broken_assets,
        "pending_reanalysis": pending_reanalysis,
        "sync_conflicts": conflicts,
    }
