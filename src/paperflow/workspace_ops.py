from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ruamel.yaml import YAML

from paperflow.data.records import UserPaperRecord
from paperflow.obsidian.frontmatter import read_note
from paperflow.obsidian.note_renderer import extract_user_notes
from paperflow.workspace import WorkspaceSettings, dump_yaml


BEIJING = ZoneInfo("Asia/Shanghai")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_workspace_backup(
    root: Path,
    *,
    label: str = "workspace",
    include_pdfs: bool = False,
) -> Path:
    destination = (
        root
        / ".paperflow/backups"
        / f"{label}-{datetime.now(BEIJING).strftime('%Y%m%d-%H%M%S')}"
    )
    destination.mkdir(parents=True, exist_ok=False)
    includes = [
        "paperflow.yaml",
        ".paperflow/workspace.yaml",
        ".paperflow/workspace.local.yaml",
        ".paperflow/state/paperflow.db",
        ".paperflow/data/papers",
        ".paperflow/data/raw",
        ".paperflow/data/ai",
        ".paperflow/data/user",
        ".paperflow/data/derived",
        ".paperflow/schemas",
        "10 Papers",
        "40 Daily Briefs",
        "50 Inbox",
        "90 System/Forms",
        "90 System/Templates",
        "90 System/Taxonomy",
        ".obsidian/community-plugins.json",
        ".obsidian/plugins/form-flow/data.json",
        ".obsidian/plugins/paperflow-automation/data.json",
    ]
    manifest: list[dict[str, Any]] = []
    for relative in includes:
        source = root / relative
        if not source.exists():
            continue
        files = [source] if source.is_file() else sorted(source.rglob("*"))
        for path in files:
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            target = destination / "files" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            manifest.append(
                {
                    "path": rel.as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                    "copied": True,
                }
            )
    for pdf in sorted((root / "80 Attachments/Papers").rglob("*.pdf")):
        rel = pdf.relative_to(root)
        item = {
            "path": rel.as_posix(),
            "size": pdf.stat().st_size,
            "sha256": _sha256(pdf),
            "copied": include_pdfs,
        }
        if include_pdfs:
            target = destination / "files" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, target)
        manifest.append(item)
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now(BEIJING).isoformat(),
                "root": str(root),
                "include_pdfs": include_pdfs,
                "files": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def export_user_data(
    root: Path, settings: WorkspaceSettings, destination: Path
) -> Path:
    sidecars = []
    for path in sorted((root / settings.paths.user_data.root).glob("*.yaml")):
        sidecars.append(
            {
                "file": path.name,
                "record": UserPaperRecord.model_validate(
                    YAML(typ="safe").load(
                        path.read_text(encoding="utf-8")
                    )
                ).model_dump(mode="json"),
            }
        )
    notes = []
    for path in sorted((root / settings.paths.note.root).rglob("*.md")):
        frontmatter, body = read_note(path)
        uid = frontmatter.get("paper_uid")
        if not uid:
            continue
        notes.append(
            {
                "paper_uid": uid,
                "user_properties": {
                    key: value
                    for key, value in frontmatter.items()
                    if key.startswith("user_")
                },
                "user_notes": extract_user_notes(body),
            }
        )
    value = {
        "format": "paperflow-user-export",
        "schema_version": 1,
        "created_at": datetime.now(BEIJING).isoformat(),
        "sidecars": sidecars,
        "notes": notes,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def import_user_data(
    root: Path, settings: WorkspaceSettings, source: Path
) -> dict[str, Any]:
    value = json.loads(source.read_text(encoding="utf-8"))
    if value.get("format") != "paperflow-user-export":
        raise ValueError("Not a PaperFlow User Data export")
    imported = 0
    conflicts = []
    user_root = root / settings.paths.user_data.root
    for item in value.get("sidecars", []):
        record = UserPaperRecord.model_validate(item["record"])
        target = user_root / Path(item["file"]).name
        if target.exists():
            existing = YAML(typ="safe").load(
                target.read_text(encoding="utf-8")
            )
            existing_record = UserPaperRecord.model_validate(existing)
            merged = dict(record.user)
            merged.update(existing_record.user)
            if merged != record.user:
                conflicts.append(record.paper_uid)
            record = record.model_copy(update={"user": merged})
        dump_yaml(target, record.model_dump(mode="json"))
        imported += 1
    return {
        "imported": imported,
        "local_values_preserved": True,
        "conflicts": sorted(set(conflicts)),
        "notes_imported": 0,
        "note_policy": "structured sidecars only; note bodies require manual merge",
    }
