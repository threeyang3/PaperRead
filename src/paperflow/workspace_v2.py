from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from paperflow.data.compose import compose_record
from paperflow.obsidian.note_renderer import render_paper
from paperflow.utils import iso_beijing
from paperflow.versioning import VERSIONS
from paperflow.workspace import (
    default_workspace_dict,
    dump_yaml,
    install_workspace_resources,
    load_workspace_settings,
)
from paperflow.workspace_ops import create_workspace_backup


MIGRATION_ID = "workspace-0002-paperflow-1.4"


def _workspace_data(root: Path) -> dict[str, Any]:
    path = root / ".paperflow/workspace.yaml"
    value = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return value


def plan_workspace_v2(root: Path) -> dict[str, Any]:
    value = _workspace_data(root)
    found = int(value.get("versions", {}).get("workspace", 1))
    if found > VERSIONS.workspace_schema_version:
        raise ValueError(
            f"Workspace schema {found} is newer than this PaperFlow build"
        )
    records = sorted((root / ".paperflow/data/papers").glob("*.json"))
    return {
        "migration_id": MIGRATION_ID,
        "from_version": found,
        "to_version": VERSIONS.workspace_schema_version,
        "paper_records": len(records),
        "will_backup": found < VERSIONS.workspace_schema_version,
        "will_install_resources": True,
        "will_render_generated_notes": found < VERSIONS.workspace_schema_version,
        "network_requests": 0,
        "ai_calls": 0,
        "preserves": [
            "user_* properties",
            "user-added tags",
            "USER_NOTES_START/END",
            "legacy Raw and AI records",
        ],
    }


def apply_workspace_v2(root: Path) -> dict[str, Any]:
    plan = plan_workspace_v2(root)
    history_path = root / ".paperflow/state/migrations/history.jsonl"
    if plan["from_version"] == VERSIONS.workspace_schema_version:
        return {
            **plan,
            "status": "already-applied",
            "verification": verify_workspace_v2(root),
        }

    backup = create_workspace_backup(root, label="pre-paperflow-1.4")
    value = _workspace_data(root)
    defaults = default_workspace_dict()
    value.setdefault("versions", {})
    value["versions"]["workspace"] = VERSIONS.workspace_schema_version
    value["versions"]["templates"] = VERSIONS.template_bundle_version
    for key in ("visuals", "relationships", "sync_compatibility", "updates"):
        value.setdefault(key, defaults[key])
    ai = value.setdefault("ai", {})
    providers = ai.setdefault("providers", {})
    providers.setdefault("chatgpt-web", defaults["ai"]["providers"]["chatgpt-web"])
    profiles = ai.setdefault("profiles", {})
    profiles.setdefault("web_analysis", defaults["ai"]["profiles"]["web_analysis"])
    dump_yaml(root / ".paperflow/workspace.yaml", value)

    _, settings = load_workspace_settings(root)
    resources = install_workspace_resources(root, settings)
    rendered: list[str] = []
    failed: list[dict[str, str]] = []
    for path in sorted((root / ".paperflow/data/papers").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        note = record.get("note_path")
        if not note:
            continue
        try:
            composed = compose_record(root, record)
            render_paper(
                root,
                composed,
                root / str(note),
                str(record.get("system_import_method") or "migration"),
            )
            rendered.append(str(note))
        except Exception as exc:
            failed.append({"record": path.name, "error": str(exc)})

    event = {
        **plan,
        "status": "applied",
        "at": iso_beijing(),
        "backup": backup.relative_to(root).as_posix(),
        "rendered": rendered,
        "failed": failed,
        "resources": resources,
        "verification": verify_workspace_v2(root),
    }
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def verify_workspace_v2(root: Path) -> dict[str, Any]:
    value = _workspace_data(root)
    required = ("visuals", "relationships", "sync_compatibility", "updates")
    missing = [key for key in required if key not in value]
    _, settings = load_workspace_settings(root)
    return {
        "ok": (
            settings.versions.workspace == VERSIONS.workspace_schema_version
            and not missing
            and "chatgpt-web" in settings.ai.providers
        ),
        "workspace_schema": settings.versions.workspace,
        "template_bundle": settings.versions.templates,
        "missing_sections": missing,
        "chatgpt_web_provider": "chatgpt-web" in settings.ai.providers,
    }
