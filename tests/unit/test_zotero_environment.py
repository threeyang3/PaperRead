from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import paperflow.zotero.environment as environment
from paperflow.cli import app
from paperflow.zotero.environment import redact_environment
from paperflow.workspace import init_workspace


def test_detect_reads_custom_data_directory_without_database_access(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "Profiles" / "default"
    profile.mkdir(parents=True)
    data = tmp_path / "Zotero Data"
    (data / "storage").mkdir(parents=True)
    (data / "zotero.sqlite").write_bytes(b"fixture")
    (profile / "prefs.js").write_text(
        'user_pref("extensions.zotero.dataDir", "Z:\\\\Zotero Data");\n'
        'user_pref("extensions.zotero.useDataDir", true);\n'
        'user_pref("extensions.zotero.httpServer.localAPI.enabled", true);\n',
        encoding="utf-8",
    )
    (profile / "extensions.json").write_text(json.dumps({"addons": [{
        "id": "paperflow-zotero@threeyang",
        "active": True,
        "userDisabled": False,
        "appDisabled": False,
        "version": "1.5.0",
    }]}), encoding="utf-8")
    profiles = tmp_path / "profiles.ini"
    profiles.write_text(
        "[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/default\nDefault=1\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(environment, "_profile_candidates", lambda: [profiles])
    monkeypatch.setattr(environment, "_executable_candidates", lambda: [tmp_path / "zotero.exe"])
    monkeypatch.setattr(environment, "_running_process", lambda: None)
    monkeypatch.setattr(environment, "_version", lambda _: "9.0.5")
    monkeypatch.setattr(environment, "_probe_api", lambda _: {"reachable": False})
    # Make the Windows-style configured path resolve to the fixture directory.
    monkeypatch.setattr(environment.os.path, "expandvars", lambda _: str(data))

    report = environment.detect_environment()
    assert report["zotero"]["installed"] is True
    assert report["zotero"]["version"] == "9.0.5"
    assert report["profiles"][0]["data_dir"]["sqlite"] is True
    assert report["profiles"][0]["data_dir"]["storage"] is True
    assert report["profiles"][0]["paperflow_plugin"]["active"] is True
    assert report["profiles"][0]["paperflow_plugin"]["version"] == "1.5.0"
    assert report["safety"] == {
        "database_modified": False,
        "database_read": False,
        "network_scope": "loopback-only",
    }


def test_redacted_report_removes_local_paths() -> None:
    value = {
        "zotero": {"executable": "C:/Zotero/zotero.exe", "process": {"pid": 1}},
        "profiles": [
            {
                "profile_path": "C:/Users/name/Profile",
                "profiles_ini": "C:/Users/name/profiles.ini",
                "prefs_path": "C:/Users/name/prefs.js",
                "plugin_dir": "C:/Users/name/extensions",
                "data_dir": {"path": "D:/Zotero", "exists": True},
            }
        ],
    }
    redacted = redact_environment(value)
    dumped = json.dumps(redacted)
    assert "C:/Users" not in dumped
    assert "D:/Zotero" not in dumped
    assert "C:/Zotero" not in dumped


def test_redacted_report_hides_edge_connector_manifest_path() -> None:
    value = {
        "browser_extensions": {
            "edge": {
                "installed": True,
                "extensions": [{"extension_id": "nmhdhpibnnopknkmonacoephklnflpho", "manifest_path": "C:/Edge/manifest.json"}],
            }
        }
    }
    redacted = redact_environment(value)
    assert "manifest_path" not in redacted["browser_extensions"]["edge"]["extensions"][0]


def test_api_probe_refuses_non_loopback() -> None:
    result = environment._probe_api("https://example.com/api/")
    assert result["reachable"] is False
    assert result["error"] == "non-loopback URL refused"


def test_detect_reports_multiple_profiles_and_unicode_space_data_dir(tmp_path: Path, monkeypatch) -> None:
    profiles_root = tmp_path / "Profiles"
    first = profiles_root / "默认 Profile"
    second = profiles_root / "Research Profile"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    first_data = tmp_path / "Zotero 数据 目录"
    second_data = tmp_path / "Zotero Research Data"
    for data in (first_data, second_data):
        (data / "storage").mkdir(parents=True)
        (data / "zotero.sqlite").write_bytes(b"fixture")
    (first / "prefs.js").write_text(
        'user_pref("extensions.zotero.dataDir", "Z:\\\\Zotero Data");\n'
        'user_pref("extensions.zotero.useDataDir", true);\n',
        encoding="utf-8",
    )
    (second / "prefs.js").write_text(
        'user_pref("extensions.zotero.dataDir", "Z:\\\\Zotero Research Data");\n'
        'user_pref("extensions.zotero.useDataDir", true);\n'
        'user_pref("extensions.zotero.httpServer.localAPI.enabled", false);\n',
        encoding="utf-8",
    )
    profiles = tmp_path / "profiles.ini"
    profiles.write_text(
        "[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/默认 Profile\nDefault=1\n\n"
        "[Profile1]\nName=research\nIsRelative=1\nPath=Profiles/Research Profile\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(environment, "_profile_candidates", lambda: [profiles])
    monkeypatch.setattr(environment, "_executable_candidates", lambda: [])
    monkeypatch.setattr(environment, "_running_process", lambda: None)
    monkeypatch.setattr(environment, "_version", lambda _: "")
    monkeypatch.setattr(environment, "_probe_api", lambda _: {"reachable": False, "error": "disabled"})
    monkeypatch.setattr(
        environment.os.path,
        "expandvars",
        lambda value: str(first_data if "Research" not in value else second_data),
    )

    report = environment.detect_environment()
    assert len(report["profiles"]) == 2
    assert report["active_profile_count"] == 1
    assert report["ambiguous_data_directory"] is True
    assert report["profiles"][0]["data_dir"]["sqlite"] is True
    assert report["profiles"][1]["local_api_enabled"] == "false"


def test_detect_missing_data_directory_is_safe(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "Profile"
    profile.mkdir()
    (profile / "prefs.js").write_text(
        'user_pref("extensions.zotero.dataDir", "Z:\\\\Missing Zotero");\n'
        'user_pref("extensions.zotero.useDataDir", true);\n',
        encoding="utf-8",
    )
    profiles = tmp_path / "profiles.ini"
    profiles.write_text("[Profile0]\nName=default\nIsRelative=1\nPath=Profile\nDefault=1\n", encoding="utf-8")
    monkeypatch.setattr(environment, "_profile_candidates", lambda: [profiles])
    monkeypatch.setattr(environment, "_executable_candidates", lambda: [])
    monkeypatch.setattr(environment, "_running_process", lambda: None)
    monkeypatch.setattr(environment, "_version", lambda _: "")
    monkeypatch.setattr(environment, "_probe_api", lambda _: {"reachable": False})
    monkeypatch.setattr(environment.os.path, "expandvars", lambda _: str(tmp_path / "Missing Zotero"))
    report = environment.detect_environment()
    assert report["zotero"]["installed"] is False
    assert report["profiles"][0]["data_dir"]["exists"] is False
    assert report["profiles"][0]["data_dir"]["sqlite"] is False


def test_zotero_cli_persists_ignored_local_state(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    init_workspace(vault)
    monkeypatch.setattr(
        environment,
        "detect_environment",
        lambda: {
            "zotero": {"installed": True},
            "profiles": [{"data_dir": {"exists": True, "sqlite": True, "storage": True}}],
            "active_profile_count": 1,
            "safety": {"network_scope": "loopback-only", "database_modified": False, "database_read": False},
        },
    )
    runner = CliRunner()
    result = runner.invoke(app, ["zotero", "detect", "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    state = vault / ".paperflow/state/zotero-environment.json"
    assert state.exists()
    assert json.loads(state.read_text(encoding="utf-8"))["zotero"]["installed"] is True


def test_zotero_status_exposes_plugin_readiness(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    init_workspace(vault)
    monkeypatch.setattr(
        environment,
        "detect_environment",
        lambda: {
            "zotero": {"installed": True},
            "profiles": [{
                "data_dir": {"exists": True, "sqlite": True, "storage": True},
                "paperflow_plugin": {"installed": True, "active": True},
            }],
            "active_profile_count": 1,
            "local_api": {"reachable": True},
            "safety": {"network_scope": "loopback-only", "database_modified": False, "database_read": False},
        },
    )
    result = CliRunner().invoke(app, ["zotero", "status", "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["paperflow_plugin"]["active"] is True
    assert payload["ready_for_plugin_integration"] is True
