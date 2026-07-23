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
from paperflow.paths.templates import safe_component
from paperflow.utils import atomic_json, iso_beijing
from paperflow.versioning import VERSIONS
from paperflow.workspace import default_workspace_dict, dump_yaml, load_workspace_settings
from paperflow.workspace_ops import create_workspace_backup


MIGRATION_ID = "workspace-0003-pdf-community-annotations"
DERIVED_PDF_PATH_KEYS = {"paper_pdf_path", "pdf_path", "source_pdf_path"}


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


def _derived_record_paths(root: Path, record: dict[str, Any]) -> list[Path]:
    paper_id = safe_component(
        str(record.get("paper_arxiv_id") or record["paper_uid"]).replace(":", "_")
    )
    candidates = [root / ".paperflow/data/derived" / f"{paper_id}.json"]
    configured = str((record.get("layer_paths") or {}).get("derived") or "")
    if configured:
        relative = Path(configured)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe Derived layer path: {configured}")
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ValueError(f"Derived layer path escapes Workspace: {configured}")
        candidates.append(candidate)
    return list(dict.fromkeys(path.resolve() for path in candidates))


def _rewrite_derived_pdf_paths(value: Any, target: str) -> int:
    """Rewrite only modeled/rebuildable PDF path fields, never asset paths."""
    changed = 0
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key in DERIVED_PDF_PATH_KEYS and item != target:
                value[key] = target
                changed += 1
            elif isinstance(item, (dict, list)):
                changed += _rewrite_derived_pdf_paths(item, target)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                changed += _rewrite_derived_pdf_paths(item, target)
    return changed


def _update_derived_pdf_paths(
    root: Path,
    record: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    updated_files = []
    updated_fields = 0
    manifests_checked = []
    for path in _derived_record_paths(root, record):
        if not path.is_file():
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        derived = value.get("derived")
        if not isinstance(derived, dict):
            raise ValueError(f"{path}: expected a DerivedRecord mapping")
        changed = _rewrite_derived_pdf_paths(derived, target)
        if changed:
            atomic_json(path, value)
            updated_files.append(path.relative_to(root).as_posix())
            updated_fields += changed
        extraction = derived.get("extraction") or {}
        for asset in extraction.get("visual_assets", []):
            asset_path = str(asset.get("path") or "")
            if not asset_path:
                continue
            manifest = (root / asset_path).parent / "manifest.json"
            if manifest.is_file():
                manifests_checked.append(manifest.relative_to(root).as_posix())
                manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
                manifest_changed = _rewrite_derived_pdf_paths(manifest_value, target)
                if manifest_changed:
                    atomic_json(manifest, manifest_value)
                    updated_fields += manifest_changed
    return {
        "files": sorted(set(updated_files)),
        "fields": updated_fields,
        "visual_manifests_checked": sorted(set(manifests_checked)),
    }


def _derived_pdf_path_mismatches(
    root: Path,
    record: dict[str, Any],
    target: str,
) -> list[str]:
    mismatches = []

    def inspect(value: Any, location: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{location}.{key}"
                if key in DERIVED_PDF_PATH_KEYS and item != target:
                    mismatches.append(f"{child}={item}")
                elif isinstance(item, (dict, list)):
                    inspect(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, (dict, list)):
                    inspect(item, f"{location}[{index}]")

    for path in _derived_record_paths(root, record):
        if not path.is_file():
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        derived = value.get("derived") or {}
        inspect(derived, path.relative_to(root).as_posix())
        extraction = derived.get("extraction") or {}
        for asset in extraction.get("visual_assets", []):
            asset_path = str(asset.get("path") or "")
            if not asset_path:
                continue
            manifest = (root / asset_path).parent / "manifest.json"
            if manifest.is_file():
                inspect(
                    json.loads(manifest.read_text(encoding="utf-8")),
                    manifest.relative_to(root).as_posix(),
                )
    return mismatches


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
    derived_repairs = []
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
        mismatches = _derived_pdf_path_mismatches(
            root,
            record,
            target.relative_to(root).as_posix(),
        )
        if mismatches:
            derived_repairs.append({
                "paper_uid": record["paper_uid"],
                "mismatches": mismatches,
            })
    return {
        "migration_id": MIGRATION_ID,
        "from_version": found,
        "to_version": VERSIONS.workspace_schema_version,
        "dry_run": True,
        "repair_mode": found == VERSIONS.workspace_schema_version,
        "records": len(pdfs),
        "pdf_copies": sum(int(item["copy_required"]) for item in pdfs),
        "missing_pdfs": missing,
        "derived_repairs": derived_repairs,
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
    if plan["from_version"] > VERSIONS.workspace_schema_version:
        raise RuntimeError(
            f"Workspace schema {plan['from_version']} is newer than schema 3"
        )
    repair_mode = bool(plan["repair_mode"])
    if repair_mode:
        backup = _backup_path(root)
        _validated_backup_files(root, backup)
    else:
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
            value.get("publishing", {}).get(
                "include_community_contributions", False
            )
        )
        for source in value.get("subscriptions", {}).get("sources", []):
            source.setdefault("capabilities", ["raw", "ai"])
        dump_yaml(workspace_path, value)

    copied = []
    updated = []
    derived_updates = []
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
            target_relative = target.relative_to(root).as_posix()
            record["paper_pdf_path"] = target_relative
            atomic_json(record_path, record)
            updated.append(record["paper_uid"])
            derived_result = _update_derived_pdf_paths(
                root,
                record,
                target_relative,
            )
            derived_updates.append({
                "paper_uid": record["paper_uid"],
                **derived_result,
            })
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
    defaults = default_workspace_dict()
    for rule in defaults["paths"].values():
        (root / rule["root"]).mkdir(parents=True, exist_ok=True)
    rebuild_bases(root)
    verification = verify_workspace_v3(root)
    event = {
        **plan,
        "dry_run": False,
        "status": (
            "verification-failed"
            if not verification["ok"]
            else "repaired" if repair_mode else "applied"
        ),
        "at": iso_beijing(),
        "backup": backup.relative_to(root).as_posix(),
        "copied_pdfs": copied,
        "updated_records": updated,
        "derived_updates": derived_updates,
        "rendered_notes": rendered,
        "verification": verification,
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
    derived_path_mismatches = []
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
        derived_path_mismatches.extend(
            _derived_pdf_path_mismatches(root, record, relative)
        )
        note_relative = str(record.get("note_path") or "")
        if note_relative:
            note = root / note_relative
            if not note.is_file():
                missing_notes.append(note_relative)
            else:
                frontmatter, body = read_note(note)
                legacy_relative = (
                    path.parent.with_suffix(".pdf").relative_to(root).as_posix()
                )
                if (
                    frontmatter.get("paper_pdf_path") != relative
                    or f"[[{relative}" not in body
                    or (
                        legacy_relative != relative
                        and legacy_relative in body
                    )
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
            and not derived_path_mismatches
            and not bases
        ),
        "workspace_schema": settings.versions.workspace,
        "pdf_template": settings.paths.pdf.template,
        "missing": missing,
        "hash_mismatches": hash_mismatches,
        "missing_notes": missing_notes,
        "note_link_mismatches": note_link_mismatches,
        "derived_path_mismatches": derived_path_mismatches,
        "base_errors": bases,
        "user_notes_modified": 0,
    }
