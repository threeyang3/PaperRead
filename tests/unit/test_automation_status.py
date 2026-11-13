from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.obsidian.automation_status import automation_status
from paperflow.workspace import init_workspace


def settings(root: Path) -> None:
    path = root / ".obsidian/plugins/paperflow-automation/data.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "enabled": True,
        "dailyLocalTime": "08:00",
        "runtime": {"lastDailyAt": "old", "lastInboxExitCode": 0},
    }), encoding="utf-8")


def test_new_runtime_overrides_legacy_and_reports_failed_tracks(tmp_path):
    settings(tmp_path)
    runtime = tmp_path / ".paperflow/runtime/plugin-state.json"
    runtime.parent.mkdir(parents=True)
    runtime.write_text(json.dumps({
        "lastDailyAt": "new",
        "lastSourceSyncExitCode": 1,
        "activeJob": "source-sync",
    }), encoding="utf-8")
    value = automation_status(tmp_path)
    assert value is not None
    assert value["last_daily_at"] == "new"
    assert value["last_source_sync_exit_code"] == 1
    assert value["last_inbox_exit_code"] == 0
    assert value["runtime_source"] == "plugin-state"
    assert value["active_job"] == "source-sync"


@pytest.mark.parametrize("payload", ["{invalid", "[]"])
def test_invalid_runtime_preserves_legacy_and_reports_error(tmp_path, payload):
    settings(tmp_path)
    runtime = tmp_path / ".paperflow/runtime/plugin-state.json"
    runtime.parent.mkdir(parents=True)
    runtime.write_text(payload, encoding="utf-8")
    value = automation_status(tmp_path)
    assert value is not None
    assert value["last_daily_at"] == "old"
    assert value["runtime_source"] == "legacy-settings"
    assert value["runtime_state_error"]


def test_status_accepts_explicit_vault_outside_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    init_workspace(vault)
    settings(vault)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["status", "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["obsidian_automation"]["last_daily_at"] == "old"
