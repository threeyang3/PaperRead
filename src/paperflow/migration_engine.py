from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from paperflow.data import split_legacy_record
from paperflow.locking import FileLock
from paperflow.paths.templates import safe_component
from paperflow.workspace import default_workspace_dict, dump_yaml
from ruamel.yaml import YAML
from jsonschema import Draft202012Validator


MIGRATION_ID = "workspace-0001-productization"
BEIJING = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(BEIJING)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class PlannedWrite:
    source: str
    target: str
    layer: str
    source_sha256: str


def _legacy_files(root: Path) -> list[Path]:
    return sorted((root / ".paperflow/data/papers").glob("*.json"))


def build_plan(root: Path, to_version: int | None = None) -> dict[str, Any]:
    if to_version not in (None, 1):
        raise ValueError("Only workspace schema version 1 is available.")
    writes: list[PlannedWrite] = []
    unknown: dict[str, list[str]] = {}
    ai_count = 0
    for source in _legacy_files(root):
        record = json.loads(source.read_text(encoding="utf-8"))
        raw, ai, user, derived = split_legacy_record(record)
        paper_id = safe_component(
            str(record.get("paper_arxiv_id") or record["paper_uid"]).replace(":", "_")
        )
        version = int(record.get("paper_arxiv_version") or 1)
        source_sha = _sha256(source)
        targets = [
            (
                root
                / ".paperflow/data/raw"
                / raw.source
                / paper_id
                / f"v{version}.json",
                "raw",
            ),
            (root / ".paperflow/data/user" / f"{paper_id}.yaml", "user"),
            (
                root / ".paperflow/data/derived" / f"{paper_id}.json",
                "derived",
            ),
        ]
        if ai is not None:
            ai_count += 1
            targets.append(
                (
                    root
                    / ".paperflow/data/ai/full_analysis"
                    / paper_id
                    / f"v{version}"
                    / f"{ai.analysis_id}.json",
                    "ai",
                )
            )
        for target, layer in targets:
            writes.append(
                PlannedWrite(
                    source=source.relative_to(root).as_posix(),
                    target=target.relative_to(root).as_posix(),
                    layer=layer,
                    source_sha256=source_sha,
                )
            )
        if raw.extensions:
            unknown[record["paper_uid"]] = sorted(raw.extensions)
    workspace = root / ".paperflow/workspace.yaml"
    if not workspace.exists():
        writes.append(
            PlannedWrite(
                source="paperflow.yaml" if (root / "paperflow.yaml").exists() else "",
                target=".paperflow/workspace.yaml",
                layer="workspace",
                source_sha256=(
                    _sha256(root / "paperflow.yaml")
                    if (root / "paperflow.yaml").exists()
                    else ""
                ),
            )
        )
    local_workspace = root / ".paperflow/workspace.local.yaml"
    if not local_workspace.exists():
        writes.append(
            PlannedWrite(
                source="",
                target=".paperflow/workspace.local.yaml",
                layer="workspace-local",
                source_sha256="",
            )
        )
    destructive = sum(
        1 for item in writes if (root / item.target).exists()
    )
    return {
        "migration_id": MIGRATION_ID,
        "from_version": 0,
        "to_version": 1,
        "data_types": ["workspace", "raw", "ai", "user", "derived"],
        "reversible": True,
        "legacy_records": len(_legacy_files(root)),
        "raw_records": len(_legacy_files(root)),
        "ai_records": ai_count,
        "user_records": len(_legacy_files(root)),
        "derived_records": len(_legacy_files(root)),
        "unknown_fields": unknown,
        "writes": [asdict(item) for item in writes],
        "network_requests": 0,
        "pdf_downloads": 0,
        "ai_calls": 0,
        "destructive_overwrites": destructive,
        "strategy": "preserve legacy files and generate versioned layer records",
    }


def status(root: Path) -> dict[str, Any]:
    history = migration_history(root)
    relevant = [
        item for item in history if item.get("migration_id") == MIGRATION_ID
    ]
    active = bool(relevant and relevant[-1].get("status") == "applied")
    return {
        "application_migration": MIGRATION_ID,
        "workspace_version": (
            1 if (root / ".paperflow/workspace.yaml").exists() else 0
        ),
        "legacy_records": len(_legacy_files(root)),
        "applied": active,
        "pending": not active,
    }


def _materialize(root: Path, staging: Path) -> tuple[list[str], list[str]]:
    created: list[str] = []
    unknown: list[str] = []
    for source in _legacy_files(root):
        record = json.loads(source.read_text(encoding="utf-8"))
        raw, ai, user, derived = split_legacy_record(record)
        unknown.extend(raw.extensions)
        paper_id = safe_component(
            str(record.get("paper_arxiv_id") or record["paper_uid"]).replace(":", "_")
        )
        version = int(record.get("paper_arxiv_version") or 1)
        outputs: list[tuple[Path, bytes]] = [
            (
                Path(".paperflow/data/raw")
                / raw.source
                / paper_id
                / f"v{version}.json",
                _json_bytes(raw.model_dump(mode="json")),
            ),
            (
                Path(".paperflow/data/user") / f"{paper_id}.yaml",
                _json_bytes(user.model_dump(mode="json")),
            ),
            (
                Path(".paperflow/data/derived") / f"{paper_id}.json",
                _json_bytes(derived.model_dump(mode="json")),
            ),
        ]
        if ai is not None:
            outputs.append(
                (
                    Path(".paperflow/data/ai/full_analysis")
                    / paper_id
                    / f"v{version}"
                    / f"{ai.analysis_id}.json",
                    _json_bytes(ai.model_dump(mode="json")),
                )
            )
        for relative, payload in outputs:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            json.loads(target.read_text(encoding="utf-8"))
            created.append(relative.as_posix())
    if not (root / ".paperflow/workspace.yaml").exists():
        workspace = staging / ".paperflow/workspace.yaml"
        dump_yaml(workspace, _legacy_workspace_dict(root))
        created.append(".paperflow/workspace.yaml")
    if not (root / ".paperflow/workspace.local.yaml").exists():
        local = staging / ".paperflow/workspace.local.yaml"
        dump_yaml(local, {"ai": {"providers": {}}})
        created.append(".paperflow/workspace.local.yaml")
    return created, sorted(set(unknown))


def _legacy_workspace_dict(root: Path) -> dict[str, Any]:
    """Map legacy settings into schema 1 without carrying the fixed Vault path."""
    data = default_workspace_dict()
    path = root / "paperflow.yaml"
    if not path.exists():
        data["workspace_name"] = root.name
        return data
    legacy = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    vault = legacy.get("vault", {})
    data["workspace_name"] = root.name
    data["timezone"] = vault.get("timezone", data["timezone"])
    data["language"] = vault.get("language", data["language"])
    data["language_fallback"] = vault.get(
        "language_fallback", data["language_fallback"]
    )
    path_mapping = {
        "paper_folder": "note",
        "pdf_folder": "pdf",
        "daily_brief_folder": "daily_brief",
        "request_folder": "inbox",
        "processed_request_folder": "processed_inbox",
        "failed_folder": "failed_inbox",
        "manual_review_folder": "manual_review",
    }
    for old, new in path_mapping.items():
        if vault.get(old):
            data["paths"][new]["root"] = str(vault[old]).replace("\\", "/")
    data["discovery"].update(legacy.get("discovery", {}))
    arxiv = legacy.get("arxiv", {})
    downloads = data["downloads"]
    downloads["enabled"] = arxiv.get("download_pdf", downloads["enabled"])
    downloads["source"] = arxiv.get("download_source", downloads["source"])
    downloads["max_pdf_size_mb"] = arxiv.get(
        "max_pdf_size_mb", downloads["max_pdf_size_mb"]
    )
    downloads["timeout_seconds"] = arxiv.get(
        "timeout_seconds", downloads["timeout_seconds"]
    )
    downloads["max_retries"] = arxiv.get(
        "max_retries", downloads["max_retries"]
    )
    downloads["request_interval_seconds"] = arxiv.get(
        "request_interval_seconds", downloads["request_interval_seconds"]
    )
    analysis = legacy.get("analysis", {})
    full = data["ai"]["profiles"]["full_analysis"]
    full["provider"] = analysis.get("provider", full["provider"])
    full["model"] = analysis.get("model", full["model"])
    full["timeout_seconds"] = analysis.get(
        "timeout_seconds", full["timeout_seconds"]
    )
    triage = data["ai"]["profiles"]["triage"]
    triage["provider"] = analysis.get(
        "relevance_provider", triage["provider"]
    )
    triage["model"] = analysis.get("relevance_model", triage["model"])
    fallback = analysis.get("fallback_provider")
    if fallback:
        data["ai"]["profiles"]["fallback_analysis"]["provider"] = fallback
    else:
        full["fallback_profile"] = ""
    form = legacy.get("form_flow", {})
    data["obsidian"]["install_form_flow"] = form.get(
        "enabled", data["obsidian"]["install_form_flow"]
    )
    automation = legacy.get("obsidian_automation", {})
    data["obsidian"]["enable_daily_automation"] = automation.get(
        "enabled", data["obsidian"]["enable_daily_automation"]
    )
    data["obsidian"]["daily_local_time"] = automation.get(
        "daily_local_time", data["obsidian"]["daily_local_time"]
    )
    data["obsidian"]["inbox_interval_minutes"] = automation.get(
        "inbox_poll_interval_minutes",
        data["obsidian"]["inbox_interval_minutes"],
    )
    data["obsidian"]["catch_up_after_missed_run"] = automation.get(
        "catch_up_after_missed_run",
        data["obsidian"]["catch_up_after_missed_run"],
    )
    return data


def _backup_sources(root: Path, backup: Path, plan: dict[str, Any]) -> None:
    sources = {
        item["source"] for item in plan["writes"] if item.get("source")
    }
    for relative in sorted(sources):
        source = root / relative
        if source.exists():
            target = backup / "original" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (backup / "plan.json").write_bytes(_json_bytes(plan))


def _record_history(root: Path, event: dict[str, Any]) -> None:
    path = root / ".paperflow/state/migrations/history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _verify_sqlite(root: Path) -> None:
    database = root / ".paperflow/state/paperflow.db"
    if not database.exists():
        return
    with sqlite3.connect(database) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {result}")


def verify(root: Path, run_id: str | None = None) -> dict[str, Any]:
    raw_root = root / ".paperflow/data/raw"
    raw = list(raw_root.rglob("*.json"))
    migrated_raw = [
        path
        for path in raw
        if "subscriptions" not in path.relative_to(raw_root).parts
    ]
    user = list((root / ".paperflow/data/user").glob("*.yaml"))
    derived = list((root / ".paperflow/data/derived").glob("*.json"))
    ai = list((root / ".paperflow/data/ai").rglob("*.json"))
    schema_root = root / ".paperflow/schemas"
    if not schema_root.exists():
        schema_root = Path(__file__).resolve().parents[2] / "schemas"
    validators = {
        "raw": Draft202012Validator(
            json.loads(
                (schema_root / "raw-paper.schema.json").read_text(
                    encoding="utf-8"
                )
            )
        ),
        "ai": Draft202012Validator(
            json.loads(
                (schema_root / "ai-analysis.schema.json").read_text(
                    encoding="utf-8"
                )
            )
        ),
        "user": Draft202012Validator(
            json.loads(
                (schema_root / "user-paper.schema.json").read_text(
                    encoding="utf-8"
                )
            )
        ),
    }
    for layer, paths in [
        ("raw", raw),
        ("ai", ai),
        ("user", user),
        ("derived", derived),
    ]:
        for path in paths:
            value = (
                YAML(typ="safe").load(path.read_text(encoding="utf-8"))
                if layer == "user"
                else json.loads(path.read_text(encoding="utf-8"))
            )
            if layer in validators:
                validators[layer].validate(value)
            if int(value.get("schema_version", 0)) < 1:
                raise RuntimeError(f"Missing schema_version in {path}")
    legacy_count = len(_legacy_files(root))
    if len(migrated_raw) != legacy_count or len(user) != legacy_count:
        raise RuntimeError(
            "Record count mismatch: "
            f"legacy={legacy_count}, migrated_raw={len(migrated_raw)}, "
            f"user={len(user)}, total_raw={len(raw)}"
        )
    _verify_sqlite(root)
    missing_notes: list[str] = []
    for source in _legacy_files(root):
        record = json.loads(source.read_text(encoding="utf-8"))
        note = record.get("note_path")
        if note and not (root / note).exists():
            missing_notes.append(note)
    if missing_notes:
        raise RuntimeError(f"Broken note paths: {missing_notes}")
    return {
        "run_id": run_id,
        "ok": True,
        "legacy_records": legacy_count,
        "raw_records": len(raw),
        "migrated_raw_records": len(migrated_raw),
        "ai_records": len(ai),
        "user_records": len(user),
        "derived_records": len(derived),
        "sqlite": "ok",
        "links": "ok",
    }


def apply(root: Path, to_version: int | None = None) -> dict[str, Any]:
    lock = root / ".paperflow/state/workspace.lock"
    with FileLock(lock):
        current = status(root)
        if current["applied"]:
            return {
                "migration_id": MIGRATION_ID,
                "status": "already-applied",
                "verification": verify(root),
                "changed": 0,
            }
        plan = build_plan(root, to_version)
        run_id = f"{MIGRATION_ID}-{_now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        base = root / ".paperflow/state/migrations"
        staging = base / "staging" / run_id
        backup = root / ".paperflow/backups" / run_id
        staging.mkdir(parents=True, exist_ok=False)
        backup.mkdir(parents=True, exist_ok=False)
        _backup_sources(root, backup, plan)
        created: list[str] = []
        installed: list[str] = []
        try:
            created, unknown = _materialize(root, staging)
            for relative in created:
                source = staging / relative
                target = root / relative
                if target.exists():
                    existing = backup / "replaced" / relative
                    existing.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, existing)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + f".{run_id}.tmp")
                shutil.copy2(source, temporary)
                temporary.replace(target)
                installed.append(relative)
            verification = verify(root, run_id)
            event = {
                "migration_id": MIGRATION_ID,
                "run_id": run_id,
                "status": "applied",
                "at": _now().isoformat(),
                "backup": backup.relative_to(root).as_posix(),
                "created": installed,
                "unknown_fields": unknown,
                "verification": verification,
            }
            (backup / "result.json").write_bytes(_json_bytes(event))
            _record_history(root, event)
            return event
        except Exception as exc:
            for relative in reversed(installed):
                target = root / relative
                replaced = backup / "replaced" / relative
                if replaced.exists():
                    shutil.copy2(replaced, target)
                else:
                    target.unlink(missing_ok=True)
            event = {
                "migration_id": MIGRATION_ID,
                "run_id": run_id,
                "status": "failed-restored",
                "at": _now().isoformat(),
                "backup": backup.relative_to(root).as_posix(),
                "error": str(exc),
            }
            _record_history(root, event)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def migration_history(root: Path) -> list[dict[str, Any]]:
    path = root / ".paperflow/state/migrations/history.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def rollback(root: Path, migration_id: str) -> dict[str, Any]:
    with FileLock(root / ".paperflow/state/workspace.lock"):
        matches = [
            item
            for item in migration_history(root)
            if item.get("migration_id") == migration_id
            or item.get("run_id") == migration_id
        ]
        applied = next(
            (item for item in reversed(matches) if item.get("status") == "applied"),
            None,
        )
        if applied is None:
            raise ValueError(f"No applied migration found for {migration_id}")
        backup = root / applied["backup"]
        for relative in reversed(applied.get("created", [])):
            target = root / relative
            replacement = backup / "replaced" / relative
            if replacement.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(replacement, target)
            else:
                target.unlink(missing_ok=True)
        event = {
            "migration_id": applied["migration_id"],
            "run_id": applied["run_id"],
            "status": "rolled-back",
            "at": _now().isoformat(),
            "backup": applied["backup"],
        }
        _record_history(root, event)
        return event
