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


def test_api_probe_refuses_non_loopback() -> None:
    result = environment._probe_api("https://example.com/api/")
    assert result["reachable"] is False
    assert result["error"] == "non-loopback URL refused"


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
