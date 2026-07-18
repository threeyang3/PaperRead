from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from paperflow.locking import FileLock
from paperflow.paths.service import preview_all
from paperflow.utils import atomic_json, atomic_write
from paperflow.workspace import WorkspaceSettings


BEIJING = ZoneInfo("Asia/Shanghai")


def plan_path_migration(
    root: Path, settings: WorkspaceSettings
) -> dict[str, Any]:
    records = preview_all(root, settings)
    moves = []
    redirects = 0
    conflicts = []
    for record in records:
        for kind in ["note", "pdf"]:
            item = record[kind]
            old = item["old_path"]
            new = item["new_path"]
            if not old or old == new:
                continue
            move = {
                "paper_uid": record["paper_uid"],
                "kind": kind,
                "old_path": old,
                "new_path": new,
                "depends_on_ai": item["depends_on_ai"],
                "conflict": item["conflict"],
            }
            moves.append(move)
            redirects += int(kind == "note")
            if item["conflict"]:
                conflicts.append(move)
    return {
        "moves": moves,
        "move_count": len(moves),
        "redirect_count": redirects,
        "conflicts": conflicts,
        "ai_dependent_moves": sum(bool(item["depends_on_ai"]) for item in moves),
    }


def migrate_paths(
    root: Path,
    settings: WorkspaceSettings,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    plan = plan_path_migration(root, settings)
    plan["dry_run"] = dry_run
    if dry_run or not plan["moves"]:
        return plan
    if plan["conflicts"] and settings.path_templates.collision_policy == "error":
        raise RuntimeError("Path migration has target conflicts; refusing to apply")
    run_id = (
        "paths-"
        + datetime.now(BEIJING).strftime("%Y%m%d-%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    backup = root / ".paperflow/backups" / run_id
    with FileLock(root / ".paperflow/state/workspace.lock"):
        changed_records: dict[str, dict[str, Any]] = {}
        installed: list[Path] = []
        try:
            for move in plan["moves"]:
                old = root / move["old_path"]
                target = root / move["new_path"]
                if not old.exists():
                    raise FileNotFoundError(f"Path migration source missing: {old}")
                if target.exists() and target.resolve() != old.resolve():
                    raise FileExistsError(f"Path migration target exists: {target}")
                snapshot = backup / "files" / move["old_path"]
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, snapshot)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".tmp")
                shutil.copy2(old, temporary)
                temporary.replace(target)
                installed.append(target)
                if move["kind"] == "note":
                    redirect = (
                        "---\n"
                        "type: paper-redirect\n"
                        "paperflow_redirect: true\n"
                        f"paper_uid: {move['paper_uid']}\n"
                        "---\n\n"
                        f"# Moved\n\n[[{Path(move['new_path']).with_suffix('').as_posix()}]]\n"
                    )
                    atomic_write(old, redirect)
                else:
                    old.unlink()
                legacy_path = (
                    root
                    / ".paperflow/data/papers"
                    / f"{str(move['paper_uid']).replace(':', '_')}.json"
                )
                record = changed_records.get(move["paper_uid"])
                if record is None:
                    record = json.loads(legacy_path.read_text(encoding="utf-8"))
                    changed_records[move["paper_uid"]] = record
                key = "note_path" if move["kind"] == "note" else "paper_pdf_path"
                record[key] = move["new_path"]
            for uid, record in changed_records.items():
                note = root / record.get("note_path", "")
                old_pdf_moves = [
                    item
                    for item in plan["moves"]
                    if item["paper_uid"] == uid and item["kind"] == "pdf"
                ]
                if note.exists() and old_pdf_moves:
                    text = note.read_text(encoding="utf-8")
                    for move in old_pdf_moves:
                        text = text.replace(move["old_path"], move["new_path"])
                    atomic_write(note, text)
                legacy_path = (
                    root
                    / ".paperflow/data/papers"
                    / f"{str(uid).replace(':', '_')}.json"
                )
                snapshot = backup / "files" / legacy_path.relative_to(root)
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy_path, snapshot)
                atomic_json(legacy_path, record)
            for move in plan["moves"]:
                if not (root / move["new_path"]).exists():
                    raise RuntimeError(f"Path migration verification failed: {move}")
            result = {
                **plan,
                "run_id": run_id,
                "backup": backup.relative_to(root).as_posix(),
                "applied": len(plan["moves"]),
            }
            (backup / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return result
        except Exception:
            for target in reversed(installed):
                target.unlink(missing_ok=True)
            for path in (backup / "files").rglob("*"):
                if path.is_file():
                    destination = root / path.relative_to(backup / "files")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
            raise
