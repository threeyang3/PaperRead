from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from packaging.version import Version
from paperflow.models import ImportRequest
from paperflow.obsidian.frontmatter import read_note


BEIJING = ZoneInfo("Asia/Shanghai")


def request_path_is_safe(root: Path, path: Path) -> bool:
    allowed = (root / "50 Inbox/Paper Requests").resolve()
    try:
        path.resolve().relative_to(allowed)
        return path.suffix.lower() == ".md"
    except ValueError:
        return False


def parse_request(path: Path) -> tuple[ImportRequest, str]:
    frontmatter, body = read_note(path)
    request = ImportRequest.model_validate(frontmatter)
    marker = "## 用户备注"
    note = body.split(marker, 1)[1].strip() if marker in body else ""
    return request, note


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle_root() -> Path:
    repository = Path(__file__).resolve().parents[3] / "integrations/obsidian-form-flow"
    if repository.exists():
        return repository
    resource = files("paperflow").joinpath("resources/integrations/obsidian-form-flow")
    with as_file(resource) as path:
        return Path(path)


def _metadata() -> tuple[Path, dict[str, Any]]:
    root = _bundle_root()
    return root, json.loads((root / "integration.json").read_text(encoding="utf-8"))


def _plugin_status(vault: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    plugin = vault / ".obsidian/plugins" / metadata["plugin_id"] / "manifest.json"
    installed = plugin.exists()
    version = ""
    compatible = False
    if installed:
        value = json.loads(plugin.read_text(encoding="utf-8"))
        version = str(value.get("version", ""))
        compatible = Version(version) >= Version(metadata["minimum_plugin_version"])
    enabled_file = vault / ".obsidian/community-plugins.json"
    enabled = False
    if enabled_file.exists():
        enabled = metadata["plugin_id"] in json.loads(
            enabled_file.read_text(encoding="utf-8")
        )
    return {
        "installed": installed,
        "enabled": enabled,
        "version": version,
        "compatible": compatible,
    }


def integration_status(vault: Path) -> dict[str, Any]:
    bundle, metadata = _metadata()
    files_status: list[dict[str, Any]] = []
    for source_name, destination_name in metadata["files"].items():
        source = bundle / source_name
        destination = vault / destination_name
        files_status.append(
            {
                "path": destination_name,
                "exists": destination.exists(),
                "matches_bundle": destination.exists()
                and _sha256(destination) == _sha256(source),
                "bundle_sha256": _sha256(source),
                "installed_sha256": _sha256(destination)
                if destination.exists()
                else "",
                "conflict_file": destination.with_name(
                    destination.name + ".new"
                ).exists(),
            }
        )
    plugin = _plugin_status(vault, metadata)
    return {
        "integration": "form-flow",
        "integration_version": metadata["integration_version"],
        "plugin": plugin,
        "files": files_status,
        "healthy": plugin["installed"]
        and plugin["enabled"]
        and plugin["compatible"]
        and all(item["matches_bundle"] for item in files_status),
    }


def try_install_official_plugin(vault: Path) -> dict[str, Any]:
    """Ask Obsidian's own CLI to install the official community plugin."""
    executable = shutil.which("obsidian")
    if not executable:
        return {
            "installed": False,
            "reason": "Obsidian CLI not found",
            "manual": "Install community plugin id `form-flow` >= 0.0.8.",
        }
    result = subprocess.run(
        [
            executable,
            f"vault={vault.name}",
            "plugin:install",
            "id=form-flow",
            "enable",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    status = _plugin_status(vault, _metadata()[1])
    return {
        "installed": status["installed"] and status["enabled"],
        "returncode": result.returncode,
        "detail": (result.stdout or result.stderr).strip()[-1000:],
        "manual": (
            ""
            if status["installed"] and status["enabled"]
            else "Install community plugin id `form-flow` >= 0.0.8."
        ),
    }


def install_or_upgrade(vault: Path, *, mode: str = "install") -> dict[str, Any]:
    if mode not in {"install", "repair", "upgrade"}:
        raise ValueError(f"Unsupported integration operation: {mode}")
    bundle, metadata = _metadata()
    plugin = _plugin_status(vault, metadata)
    if not plugin["installed"]:
        raise RuntimeError(
            "Official Form Flow is not installed. Install plugin id `form-flow` "
            f">= {metadata['minimum_plugin_version']} first."
        )
    if not plugin["compatible"]:
        raise RuntimeError(
            f"Form Flow {plugin['version']} is too old; "
            f">= {metadata['minimum_plugin_version']} is required."
        )
    state_path = vault / ".paperflow/state/integrations/form-flow.json"
    previous: dict[str, str] = {}
    if state_path.exists():
        previous = json.loads(state_path.read_text(encoding="utf-8")).get(
            "installed_hashes", {}
        )
    backup = (
        vault
        / ".paperflow/backups"
        / f"form-flow-{datetime.now(BEIJING).strftime('%Y%m%d-%H%M%S')}"
    )
    installed_hashes: dict[str, str] = {}
    actions: list[dict[str, str]] = []
    for source_name, destination_name in metadata["files"].items():
        source = bundle / source_name
        destination = vault / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_hash = _sha256(source)
        installed_hashes[destination_name] = source_hash
        if not destination.exists():
            shutil.copy2(source, destination)
            actions.append({"path": destination_name, "action": "installed"})
            continue
        current_hash = _sha256(destination)
        if current_hash == source_hash:
            actions.append({"path": destination_name, "action": "unchanged"})
            continue
        if previous.get(destination_name) == current_hash:
            backup_target = backup / destination_name
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup_target)
            temporary = destination.with_name(destination.name + ".tmp")
            shutil.copy2(source, temporary)
            temporary.replace(destination)
            actions.append({"path": destination_name, "action": "upgraded"})
            continue
        conflict = destination.with_name(destination.name + ".new")
        shutil.copy2(source, conflict)
        actions.append(
            {
                "path": destination_name,
                "action": "merge-review",
                "candidate": conflict.relative_to(vault).as_posix(),
            }
        )
        installed_hashes[destination_name] = current_hash
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "integration": "form-flow",
        "integration_version": metadata["integration_version"],
        "plugin_version": plugin["version"],
        "updated_at": datetime.now(BEIJING).isoformat(),
        "installed_hashes": installed_hashes,
        "actions": actions,
    }
    temporary_state = state_path.with_name(state_path.name + ".tmp")
    temporary_state.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_state.replace(state_path)
    return state
