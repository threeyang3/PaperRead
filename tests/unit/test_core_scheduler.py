from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from paperflow.scheduler.core import BEIJING, CoreScheduler
from paperflow.zotero.core_service import PaperFlowCoreService
from paperflow.zotero.store import state_root


def configured(tmp_path: Path, monkeypatch):
    service = PaperFlowCoreService(tmp_path, port=0)
    scheduler = service.scheduler
    policy = dict(owner="core", daily=True, daily_time="08:00", inbox_minutes=5,
                  source_minutes=60, sources=False, inbox_path=tmp_path / "inbox")
    monkeypatch.setattr(scheduler, "policy", lambda: policy)
    return service, scheduler, policy


def test_daily_catchup_survives_scheduler_restart(tmp_path, monkeypatch):
    service, scheduler, policy = configured(tmp_path, monkeypatch)
    scheduler.tick(datetime(2026, 10, 12, 7, 59, tzinfo=BEIJING))
    assert not service.list_jobs()["jobs"]
    scheduler.tick(datetime(2026, 10, 12, 8, 30, tzinfo=BEIJING))
    job = service.list_jobs()["jobs"][0]
    assert job["kind"] == "daily"
    # A failed attempt is visible and explicitly retryable; never loop each tick.
    path = state_root(tmp_path) / "jobs" / f'{job["job_id"]}.json'
    job.update(status="failed", created_at="2026-10-12T00:30:00+00:00")
    path.write_text(json.dumps(job), encoding="utf-8")
    restarted = CoreScheduler(service)
    monkeypatch.setattr(restarted, "policy", lambda: policy)
    restarted.tick(datetime(2026, 10, 12, 23, 0, tzinfo=BEIJING))
    assert len(service.list_jobs()["jobs"]) == 1
    restarted.tick(datetime(2026, 10, 13, 8, 0, tzinfo=BEIJING))
    assert len(service.list_jobs()["jobs"]) == 2


def test_active_job_and_obsidian_ownership_prevent_duplicate(tmp_path, monkeypatch):
    service, scheduler, policy = configured(tmp_path, monkeypatch)
    policy["owner"] = "obsidian"
    now = datetime(2026, 10, 12, 9, 0, tzinfo=BEIJING)
    scheduler.tick(now)
    assert not service.list_jobs()["jobs"]
    policy["owner"] = "core"
    service.enqueue_scheduled("inbox", trigger="test")
    scheduler.tick(now)
    assert len(service.list_jobs()["jobs"]) == 1


def test_invalid_time_does_not_enqueue(tmp_path, monkeypatch):
    service, scheduler, policy = configured(tmp_path, monkeypatch)
    policy["daily_time"] = "25:10"
    assert "HH:MM" in scheduler.tick()["error"]
    assert not service.list_jobs()["jobs"]


def test_subscription_interval_and_empty_inbox(tmp_path, monkeypatch):
    service, scheduler, policy = configured(tmp_path, monkeypatch)
    policy.update(daily=False, sources=False)
    now = datetime(2026, 10, 12, 9, 0, tzinfo=BEIJING)
    scheduler.tick(now)
    assert not service.list_jobs()["jobs"]
    policy["sources"] = True
    calls = []
    monkeypatch.setattr(service, "enqueue_scheduled", lambda kind, **kw: calls.append(kind) or {"job_id": "test"})
    job_root = state_root(tmp_path) / "jobs"
    job_root.mkdir(parents=True, exist_ok=True)
    (job_root / "recent.json").write_text(json.dumps({"kind": "subscription-sync", "status": "completed",
                                                     "created_at": "2026-10-12T00:30:00Z"}), encoding="utf-8")
    scheduler.tick(now)
    assert calls == []
    scheduler.tick(datetime(2026, 10, 12, 9, 31, tzinfo=BEIJING))
    assert calls == ["subscription-sync"]


def test_existing_obsidian_daily_marker_prevents_same_day_catchup(tmp_path, monkeypatch):
    service, scheduler, policy = configured(tmp_path, monkeypatch)
    monkeypatch.setattr("paperflow.scheduler.core.standalone", lambda root: False)
    runtime = tmp_path / ".paperflow/runtime/plugin-state.json"
    runtime.parent.mkdir(parents=True)
    runtime.write_text(json.dumps({"lastDailyAt": "2026-10-12T00:05:00Z"}), encoding="utf-8")
    scheduler.tick(datetime(2026, 10, 12, 9, 0, tzinfo=BEIJING))
    assert not service.list_jobs()["jobs"]


def test_daily_worker_persists_partial_failure_and_runtime_marker(tmp_path, monkeypatch):
    service, _, _ = configured(tmp_path, monkeypatch)
    workspace = tmp_path / ".paperflow/workspace.yaml"
    workspace.parent.mkdir(parents=True, exist_ok=True)
    workspace.write_text("workspace_name: test", encoding="utf-8")
    monkeypatch.setattr("paperflow.config.load_config", lambda root: object())
    monkeypatch.setattr("paperflow.pipeline.daily.run_daily", lambda cfg: {"stats": {"failed": 1}, "errors": ["network unavailable"]})
    queued = service.enqueue_scheduled("daily", trigger="test")
    service._run_job(service.job(queued["job_id"]))
    assert service.job(queued["job_id"])["status"] == "failed"
    runtime = json.loads((tmp_path / ".paperflow/runtime/plugin-state.json").read_text(encoding="utf-8"))
    assert runtime["lastDailyExitCode"] == 1
    assert runtime["lastDailyDate"]


def test_core_respects_existing_ui_automation_times(tmp_path, monkeypatch):
    from types import SimpleNamespace
    service = PaperFlowCoreService(tmp_path, port=0)
    options = SimpleNamespace(scheduler_owner="core", enable_daily_automation=True,
                              daily_local_time="08:00", inbox_interval_minutes=5)
    settings = SimpleNamespace(obsidian=options, subscriptions=SimpleNamespace(sources=[]),
                               paths=SimpleNamespace(inbox=SimpleNamespace(root="50 Inbox/Requests")))
    monkeypatch.setattr("paperflow.workspace.load_workspace_settings", lambda root: (root, settings))
    path = tmp_path / ".obsidian/plugins/paperflow-automation/data.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"dailyLocalTime": "10:30", "inboxIntervalMinutes": 15,
                                "enabled": False}), encoding="utf-8")
    policy = service.scheduler.policy()
    assert policy["daily_time"] == "10:30" and policy["inbox_minutes"] == 15
    assert not policy["daily"] and not policy["sources"] and not policy["inbox_enabled"]
