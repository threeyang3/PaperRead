"""Safe, read-only discovery of a local Zotero installation.

The detector deliberately does not open or modify ``zotero.sqlite``. It reads
the active profile configuration, checks the configured data directory shape,
and probes the loopback Local API only when Zotero is already running.
"""

from __future__ import annotations

import configparser
import json
import os
import platform
import re
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_PREF_RE = re.compile(
    r'user_pref\("(?P<key>extensions\.zotero\.[^"]+)",\s*(?P<value>.+?)\);?\s*$'
)
_DEFAULT_API_URL = "http://127.0.0.1:23119/api/"
_ZOTERO_CONNECTOR_ID = "nmhdhpibnnopknkmonacoephklnflpho"
_PAPERFLOW_PLUGIN_ID = "paperflow-zotero@threeyang"


def _unescape_pref(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
        return value.replace('\\\\', '\\').replace('\\"', '"')
    return value


def _profile_candidates() -> list[Path]:
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
    candidates = [
        appdata / "Zotero/Zotero/profiles.ini",
        appdata / "Zotero/profiles.ini",
        home / ".zotero/zotero/profiles.ini",
        home / "Library/Application Support/Zotero/Profiles/profiles.ini",
    ]
    return list(dict.fromkeys(path for path in candidates if path.is_file()))


def _read_profiles(path: Path) -> list[dict[str, Any]]:
    parser = configparser.RawConfigParser()
    parser.read(path, encoding="utf-8")
    result: list[dict[str, Any]] = []
    for section in parser.sections():
        if not section.casefold().startswith("profile"):
            continue
        raw = dict(parser.items(section))
        value = raw.get("path", "")
        profile = Path(value)
        if raw.get("isrelative", "1") == "1":
            profile = path.parent / profile
        result.append(
            {
                "name": raw.get("name", section),
                "default": raw.get("default", "0") == "1",
                "profile_path": str(profile.expanduser()),
                "profile_exists": profile.is_dir(),
            }
        )
    return result


def _prefs(profile: Path) -> dict[str, str]:
    path = profile / "prefs.js"
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _PREF_RE.search(line)
        if match:
            values[match.group("key")] = _unescape_pref(match.group("value"))
    return values


def _executable_candidates() -> list[Path]:
    candidates: list[Path] = []
    for value in (
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if not value:
            continue
        root = Path(value)
        candidates.extend(
            [root / "Zotero/zotero.exe", root / "Programs/Zotero/zotero.exe"]
        )
    return list(dict.fromkeys(path for path in candidates if path.is_file()))


def _running_process() -> dict[str, Any] | None:
    if os.name != "nt":
        return None
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='zotero.exe'\" | "
                "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        value = json.loads(completed.stdout.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not value:
        return None
    if isinstance(value, list):
        value = value[0]
    return {
        "pid": value.get("ProcessId"),
        "executable": value.get("ExecutablePath") or "",
        "command_line_present": bool(value.get("CommandLine")),
    }


def _version(executable: Path | None) -> str:
    if executable is None or not executable.exists():
        return ""
    if os.name == "nt":
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Item -LiteralPath {json.dumps(str(executable))}).VersionInfo.ProductVersion",
                ],
                capture_output=True,
                check=False,
                timeout=5,
            )
            value = completed.stdout.decode("utf-8", errors="replace").strip()
            if value:
                return value
        except (OSError, subprocess.SubprocessError):
            pass
    return ""


def _probe_api(url: str = _DEFAULT_API_URL, timeout: float = 0.8) -> dict[str, Any]:
    host = (urlparse(url).hostname or "").casefold()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return {
            "enabled": False,
            "reachable": False,
            "error": "non-loopback URL refused",
        }
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1024)
            return {
                "enabled": True,
                "reachable": True,
                "status": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "body_prefix": body.decode("utf-8", errors="replace")[:200],
            }
    except urllib.error.HTTPError as exc:
        with exc:
            return {"enabled": True, "reachable": True, "status": exc.code}
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return {"enabled": "unknown", "reachable": False, "error": type(exc).__name__}


def _data_dir(profile: Path, prefs: dict[str, str]) -> Path:
    configured = prefs.get("extensions.zotero.dataDir", "").strip()
    if configured and prefs.get("extensions.zotero.useDataDir", "true").casefold() == "true":
        return Path(os.path.expandvars(configured)).expanduser()
    return profile


def _data_shape(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_dir(),
        "sqlite": (path / "zotero.sqlite").is_file(),
        "storage": (path / "storage").is_dir(),
        "logs": (path / "logs").is_dir(),
    }


def _paperflow_plugin(profile: Path) -> dict[str, Any]:
    """Read the public extension registry, without opening Zotero storage."""
    state_path = profile / "extensions.json"
    if not state_path.is_file():
        return {"installed": False, "active": False, "id": _PAPERFLOW_PLUGIN_ID}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"installed": False, "active": False, "id": _PAPERFLOW_PLUGIN_ID, "error": "invalid-extensions-registry"}
    addons = state.get("addons") if isinstance(state, dict) else []
    addon = next((item for item in addons or [] if isinstance(item, dict) and item.get("id") == _PAPERFLOW_PLUGIN_ID), None)
    if not addon:
        return {"installed": False, "active": False, "id": _PAPERFLOW_PLUGIN_ID}
    return {
        "installed": True,
        "active": bool(addon.get("active")),
        "user_disabled": bool(addon.get("userDisabled")),
        "app_disabled": bool(addon.get("appDisabled")),
        "version": str(addon.get("version") or ""),
        "id": _PAPERFLOW_PLUGIN_ID,
    }


def _edge_connector() -> dict[str, Any]:
    """Detect Zotero Connector manifests without reading browser history/data."""
    if os.name != "nt":
        return {"installed": False, "browser": "edge", "extensions": []}
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return {"installed": False, "browser": "edge", "extensions": []}
    user_data = Path(local_app_data) / "Microsoft/Edge/User Data"
    if not user_data.is_dir():
        return {"installed": False, "browser": "edge", "extensions": []}
    extensions: list[dict[str, Any]] = []
    profiles = [
        path for path in user_data.iterdir()
        if path.is_dir() and (path.name == "Default" or path.name.startswith("Profile "))
    ]
    for profile in sorted(profiles):
        extension_root = profile / "Extensions"
        if not extension_root.is_dir():
            continue
        for extension_id in sorted(extension_root.iterdir()):
            if not extension_id.is_dir():
                continue
            if extension_id.name != _ZOTERO_CONNECTOR_ID:
                continue
            versions = sorted(extension_id.iterdir(), reverse=True)
            for version in versions:
                manifest_path = version / "manifest.json"
                if not manifest_path.is_file():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    manifest = {}
                extensions.append({
                    "profile": profile.name,
                    "extension_id": extension_id.name,
                    "version": str(manifest.get("version") or version.name),
                    "name": str(manifest.get("name") or "Zotero Connector"),
                    "manifest_path": str(manifest_path),
                })
                break
    return {
        "installed": bool(extensions),
        "browser": "edge",
        "connector_id": _ZOTERO_CONNECTOR_ID,
        "extensions": extensions,
    }


def detect_environment(*, api_url: str = _DEFAULT_API_URL) -> dict[str, Any]:
    profiles_files = _profile_candidates()
    profile_records: list[dict[str, Any]] = []
    for profiles_file in profiles_files:
        for record in _read_profiles(profiles_file):
            profile = Path(record["profile_path"])
            prefs = _prefs(profile)
            data_dir = _data_dir(profile, prefs)
            record.update(
                {
                    "profiles_ini": str(profiles_file),
                    "data_dir": _data_shape(data_dir),
                    "local_api_enabled": prefs.get(
                        "extensions.zotero.httpServer.localAPI.enabled", ""
                    ),
                    "prefs_path": str(profile / "prefs.js"),
                    "plugin_dir": str(profile / "extensions"),
                    "paperflow_plugin": _paperflow_plugin(profile),
                }
            )
            profile_records.append(record)
    executable_candidates = _executable_candidates()
    running = _running_process()
    executable: Path | None = None
    if running and running.get("executable"):
        executable = Path(str(running["executable"]))
    elif len(executable_candidates) == 1:
        executable = executable_candidates[0]
    result = {
        "schema_version": 1,
        "platform": platform.platform(),
        "zotero": {
            "installed": bool(executable_candidates or executable),
            "executable": str(executable) if executable else "",
            "executable_candidates": [str(path) for path in executable_candidates],
            "version": _version(executable),
            "running": bool(running),
            "process": running,
        },
        "profiles": profile_records,
        "active_profile_count": sum(1 for record in profile_records if record.get("default")),
        "ambiguous_data_directory": len(
            {record["data_dir"]["path"] for record in profile_records if record["data_dir"]["exists"]}
        )
        > 1,
        "local_api": _probe_api(api_url),
        "browser_extensions": {"edge": _edge_connector()},
        "safety": {
            "database_modified": False,
            "database_read": False,
            "network_scope": "loopback-only",
        },
    }
    return result


def redact_environment(value: dict[str, Any]) -> dict[str, Any]:
    """Return a publish-safe report with local paths and process details removed."""
    result = json.loads(json.dumps(value, ensure_ascii=False))
    result.get("zotero", {}).pop("executable", None)
    result.get("zotero", {}).pop("executable_candidates", None)
    result.get("zotero", {}).pop("process", None)
    for browser in result.get("browser_extensions", {}).values():
        for extension in browser.get("extensions", []) if isinstance(browser, dict) else []:
            if isinstance(extension, dict):
                extension.pop("manifest_path", None)
    for profile in result.get("profiles", []):
        profile.pop("profiles_ini", None)
        profile.pop("prefs_path", None)
        profile.pop("plugin_dir", None)
        profile.pop("profile_path", None)
        if isinstance(profile.get("data_dir"), dict):
            profile["data_dir"].pop("path", None)
    return result


__all__ = ["detect_environment", "redact_environment"]
