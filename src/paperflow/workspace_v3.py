from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from paperflow.annotations.pdf_versions import build_pdf_index
from paperflow.config import load_config
from paperflow.obsidian.bases import rebuild_bases, validate_bases
from paperflow.obsidian.frontmatter import read_note
from paperflow.pipeline.render import render_uid
from paperflow.utils import atomic_json, iso_beijing
from paperflow.versioning import VERSIONS
from paperflow.workspace import default_workspace_dict, dump_yaml, load_workspace_settings
from paperflow.workspace_ops import create_workspace_backup


MIGRATION_ID = "workspace-0003-pdf-community-annotations"


def _yaml(path: Path) -> dict[str, Any]:
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a mapping")
    return value


def _records(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    result = []
    for path in sorted((root / ".paperflow/data/papers").glob("*.json")):
        result.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return result


def _target_pdf(root: Path, record: dict[str, Any]) -> Path:
    year = str(record.get("paper_year") or "Unclassified")
    paper_id = str(
        record.get("paper_arxiv_id") or record["paper_uid"]
    ).replace(":", "_")
    version = int(record.get("paper_arxiv_version") or 1)
    return root / "80 Attachments/Papers" / year / paper_id / f"v{version}.pdf"


def _backup_path(root: Path, backup: Path | None = None) -> Path:
    backup_root = (root / ".paperflow/backups").resolve()
    if backup is None:
        candidates = sorted(backup_root.glob("pre-paperflow-1.5-*"))
        if not candidates:
            raise FileNotFoundError("No pre-paperflow-1.5 backup exists")
        selected = candidates[-1].resolve()
    else:
        selected = (backup if backup.is_absolute() else root / backup).resolve()
    if not selected.is_relative_to(backup_root):
        raise ValueError("Workspace v3 rollback backup must be under .paperflow/backups")
    if not selected.name.startswith("pre-paperflow-1.5-"):
        raise ValueError("Workspace v3 rollback requires a pre-paperflow-1.5 backup")
    return selected


def _validated_backup_files(root: Path, backup: Path) -> list[dict[str, Any]]:
    manifest_path = backup / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Backup manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("include_pdfs") is not True:
        raise ValueError("Workspace v3 rollback requires a backup containing PDFs")
    files = []
    for item in manifest.get("files", []):
        if not item.get("copied"):
            continue
        relative = Path(str(item["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe backup manifest path: {relative}")
        source = backup / "files" / relative
        if not source.is_file():
            raise FileNotFoundError(f"Backup file missing: {source}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Backup checksum mismatch: {relative.as_posix()}")
        files.append({**item, "path": relative.as_posix()})
    if not files:
        raise ValueError("Workspace v3 backup contains no restorable files")
    return files


def plan_workspace_v3(root: Path) -> dict[str, Any]:
    workspace = _yaml(root / ".paperflow/workspace.yaml")
    found = int(workspace.get("versions", {}).get("workspace", 1))
    pdfs = []
    missing = []
    for _, record in _records(root):
        relative = str(record.get("paper_pdf_path") or "")
        source = root / relative if relative else None
        target = _target_pdf(root, record)
        item = {
            "paper_uid": record["paper_uid"],
            "from": relative,
            "to": target.relative_to(root).as_posix(),
            "version": int(record.get("paper_arxiv_version") or 1),
            "copy_required": bool(source and source.exists() and source != target),
        }
        pdfs.append(item)
        if source and not source.exists():
            missing.append(item)
    return {
        "migration_id": MIGRATION_ID,
        "from_version": found,
        "to_version": VERSIONS.workspace_schema_version,
        "dry_run": True,
        "records": len(pdfs),
        "pdf_copies": sum(int(item["copy_required"]) for item in pdfs),
        "missing_pdfs": missing,
        "new_roots": [
            "60 Annotations", "60 Reviews", "70 Community",
            ".paperflow/data/user/annotations",
            ".paperflow/data/community/subscriptions",
            ".paperflow/data/community/outbox",
            ".paperflow/data/derived/pdf-index",
        ],
        "writes_user_notes": False,
        "deletes_old_pdfs": False,
        "network_requests": 0,
        "ai_calls": 0,
        "pdf_plan": pdfs,
    }


def apply_workspace_v3(root: Path) -> dict[str, Any]:
    plan = plan_workspace_v3(root)
    if plan["from_version"] == VERSIONS.workspace_schema_version:
        return {**plan, "dry_run": False, "status": "already-applied",
                "verification": verify_workspace_v3(root)}
    backup = create_workspace_backup(
        root, label="pre-paperflow-1.5", include_pdfs=True
    )
    workspace_path = root / ".paperflow/workspace.yaml"
    value = _yaml(workspace_path)
    defaults = default_workspace_dict()
    value.setdefault("versions", {}).update(defaults["versions"])
    value.setdefault("paths", {})
    for key, rule in defaults["paths"].items():
        value["paths"].setdefault(key, rule)
    value["paths"]["pdf"]["template"] = "{{year}}/{{paper_id}}/v{{version}}.pdf"
    value.setdefault("annotations", defaults["annotations"])
    value.setdefault("community", defaults["community"])
    value.setdefault("publishing", {})[
        "include_community_contributions"
    ] = bool(
        value.get("publishing", {}).get("include_community_contributions", False)
    )
    for source in value.get("subscriptions", {}).get("sources", []):
        source.setdefault("capabilities", ["raw", "ai"])
    dump_yaml(workspace_path, value)

    copied = []
    updated = []
    for record_path, record in _records(root):
        old_relative = str(record.get("paper_pdf_path") or "")
        source = root / old_relative if old_relative else None
        target = _target_pdf(root, record)
        if source and source.exists() and source.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(
                    source.read_bytes()
                ).digest():
                    raise RuntimeError(f"PDF version collision: {target}")
            else:
                shutil.copy2(source, target)
                copied.append(target.relative_to(root).as_posix())
        if target.exists():
            record["paper_pdf_path"] = target.relative_to(root).as_posix()
            atomic_json(record_path, record)
            updated.append(record["paper_uid"])
            versions = []
            for item in sorted(target.parent.glob("v*.pdf")):
                try:
                    version = int(item.stem.removeprefix("v"))
                except ValueError:
                    continue
                versions.append({
                    "version": version,
                    "path": item.relative_to(root).as_posix(),
                })
            build_pdf_index(
                root, record["paper_uid"], versions,
                current_version=int(record.get("paper_arxiv_version") or 1),
            )
    rendered = []
    cfg = load_config(root)
    for record_path, record in _records(root):
        note_relative = str(record.get("note_path") or "")
        if not note_relative or not (root / note_relative).is_file():
            continue
        render_uid(cfg, str(record["paper_uid"]))
        rendered.append(note_relative)
    for rule in defaults["paths"].values():
        (root / rule["root"]).mkdir(parents=True, exist_ok=True)
    rebuild_bases(root)
    event = {
        **plan,
        "dry_run": False,
        "status": "applied",
        "at": iso_beijing(),
        "backup": backup.relative_to(root).as_posix(),
        "copied_pdfs": copied,
        "updated_records": updated,
        "rendered_notes": rendered,
        "verification": verify_workspace_v3(root),
    }
    history = root / ".paperflow/state/migrations/history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def plan_workspace_v3_rollback(
    root: Path,
    backup: Path | None = None,
) -> dict[str, Any]:
    selected = _backup_path(root, backup)
    files = _validated_backup_files(root, selected)
    return {
        "migration_id": MIGRATION_ID,
        "dry_run": True,
        "backup": selected.relative_to(root).as_posix(),
        "restore_files": [item["path"] for item in files],
        "restore_count": len(files),
        "delete_files": [],
        "deletes_user_files": False,
        "policy": (
            "restore checksummed backup files; preserve every path absent from "
            "the backup, including migration-created or later user files"
        ),
    }


def rollback_workspace_v3(
    root: Path,
    backup: Path | None = None,
) -> dict[str, Any]:
    plan = plan_workspace_v3_rollback(root, backup)
    selected = root / plan["backup"]
    for relative_text in plan["restore_files"]:
        relative = Path(relative_text)
        source = selected / "files" / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".paperflow-rollback.tmp")
        shutil.copy2(source, temporary)
        temporary.replace(target)
    result = {
        **plan,
        "dry_run": False,
        "status": "rolled-back",
        "restored": plan["restore_count"],
        "deleted": 0,
        "at": iso_beijing(),
    }
    history = root / ".paperflow/state/migrations/history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result


def verify_workspace_v3(root: Path) -> dict[str, Any]:
    _, settings = load_workspace_settings(root)
    missing = []
    hash_mismatches = []
    missing_notes = []
    note_link_mismatches = []
    for _, record in _records(root):
        relative = str(record.get("paper_pdf_path") or "")
        if not relative:
            continue
        path = root / relative
        if not path.exists():
            missing.append(relative)
            continue
        index = (
            root / ".paperflow/data/derived/pdf-index"
            / f"{record['paper_uid'].replace(':', '_')}.json"
        )
        if not index.exists():
            missing.append(index.relative_to(root).as_posix())
            continue
        value = json.loads(index.read_text(encoding="utf-8"))
        entry = next(
            (item for item in value["versions"] if item["path"] == relative),
            None,
        )
        if not entry or entry["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            hash_mismatches.append(relative)
        note_relative = str(record.get("note_path") or "")
        if note_relative:
            note = root / note_relative
            if not note.is_file():
                missing_notes.append(note_relative)
            else:
                frontmatter, body = read_note(note)
                if (
                    frontmatter.get("paper_pdf_path") != relative
                    or f"[[{relative}]]" not in body
                ):
                    note_link_mismatches.append(note_relative)
    bases = validate_bases(
        root,
        base_root=settings.paths.base.root,
        paper_root=settings.paths.note.root,
    )
    return {
        "ok": (
            not missing
            and not hash_mismatches
            and not missing_notes
            and not note_link_mismatches
            and not bases
        ),
        "workspace_schema": settings.versions.workspace,
        "pdf_template": settings.paths.pdf.template,
        "missing": missing,
        "hash_mismatches": hash_mismatches,
        "missing_notes": missing_notes,
        "note_link_mismatches": note_link_mismatches,
        "base_errors": bases,
        "user_notes_modified": 0,
    }
