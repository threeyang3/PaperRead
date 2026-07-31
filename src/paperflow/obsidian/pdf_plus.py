from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from paperflow.utils import atomic_json, atomic_write, iso_beijing


PLUGIN_ID = "pdf-plus"
SUPPORTED = SpecifierSet(">=0.40.7,<1.0.0")


def _resource_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[3] / "integrations/obsidian-pdf-plus",
        Path(__file__).resolve().parents[1] / "resources/integrations/obsidian-pdf-plus",
    ]
    return next((item for item in candidates if item.exists()), candidates[0])


def status(vault: Path) -> dict[str, Any]:
    plugin = vault / ".obsidian/plugins" / PLUGIN_ID
    manifest_path = plugin / "manifest.json"
    if not manifest_path.exists():
        return {
            "plugin_id": PLUGIN_ID,
            "installed": False,
            "compatible": False,
            "fallback": "native-page-link",
            "link_capability": "page",
            "selection_capture": "manual-page-and-text",
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = str(manifest.get("version", "0"))
    return {
        "plugin_id": PLUGIN_ID,
        "installed": True,
        "version": version,
        "compatible": Version(version) in SUPPORTED,
        "manifest": manifest,
        "paperflow_calls_pdf_plus_private_api": False,
        "obsidian_command_boundary": "unstable-feature-detected",
        "link_capability": "page-and-selection",
        "selection_capture": "feature-detected-command-and-clipboard",
        "selection_command": "pdf-plus:copy-link-to-selection",
        "fallback": "native-page-link",
    }


def install(vault: Path, *, dry_run: bool = True) -> dict[str, Any]:
    result = status(vault)
    if result["installed"]:
        return {**result, "dry_run": dry_run, "action": "none"}
    command = ["obsidian", f"vault={vault.name}", "plugin:install", f"id={PLUGIN_ID}"]
    if dry_run:
        return {
            **result,
            "dry_run": True,
            "action": "official-obsidian-install",
            "command": command,
        }
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(completed.stderr or completed.stdout)
    return {**status(vault), "dry_run": False, "action": "official-obsidian-install"}


def configure(vault: Path, *, repair: bool = False, dry_run: bool = True) -> dict[str, Any]:
    current = status(vault)
    if not current["installed"]:
        raise RuntimeError("Install the official PDF++ plugin first")
    source = _resource_root()
    plugin_data = vault / ".obsidian/plugins/pdf-plus/data.json"
    recommended = json.loads((source / "recommended-settings.json").read_text(encoding="utf-8"))
    existing = (
        json.loads(plugin_data.read_text(encoding="utf-8"))
        if plugin_data.exists() else {}
    )
    conflicts = [
        key for key, value in recommended.items()
        if key in existing and existing[key] != value
    ]
    candidate = plugin_data.with_name("data.json.new")
    merged = dict(existing)
    for key, value in recommended.items():
        merged.setdefault(key, value)
    if conflicts and not repair:
        target = candidate
        action = "merge-review"
    else:
        target = plugin_data
        action = "configured"
    css_target = vault / ".obsidian/snippets/paperflow-pdf-plus.css"
    result = {
        **current,
        "dry_run": dry_run,
        "action": action,
        "conflicts": conflicts,
        "settings_target": target.relative_to(vault).as_posix(),
        "css_target": css_target.relative_to(vault).as_posix(),
        "direct_pdf_editing": False,
    }
    if not dry_run:
        backup = vault / ".paperflow/backups/integrations" / f"pdf-plus-{iso_beijing().replace(':', '-')}"
        backup.mkdir(parents=True, exist_ok=False)
        if plugin_data.exists():
            shutil.copy2(plugin_data, backup / "data.json")
        atomic_json(target, merged)
        atomic_write(css_target, (source / "styles.css").read_text(encoding="utf-8"))
    return result
