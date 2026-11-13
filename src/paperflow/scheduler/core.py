"""Core-owned scheduling with durable jobs and a Beijing wall clock."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from paperflow.zotero.store import state_root, standalone

BEIJING = ZoneInfo("Asia/Shanghai")


def timestamp(value: object) -> datetime | None:
    try:
        date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return date.replace(tzinfo=BEIJING) if date.tzinfo is None else date.astimezone(BEIJING)
    except (ValueError, TypeError):
        return None


def read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path.name}")
    return value


class CoreScheduler:
    def __init__(self, service: Any):
        self.service = service
        self.root = service.root
        self.status: dict[str, Any] = {"owner": "obsidian", "last_tick_at": None, "error": None}

    def policy(self) -> dict[str, Any]:
        if standalone(self.root):
            from ruamel.yaml import YAML
            config = self.root / "config.yaml"
            raw = YAML(typ="safe").load(config.read_text(encoding="utf-8")) if config.exists() else {}
            options = (raw or {}).get("scheduler", {})
            interval = int(options.get("subscription_interval_minutes", 60))
            if not 1 <= interval <= 1440:
                raise ValueError("subscription interval must be 1..1440 minutes")
            return {"owner": "core" if options.get("enabled", False) else "obsidian", "daily": False,
                    "daily_time": "08:00", "inbox_minutes": 5, "source_minutes": interval,
                    "sources": bool(((raw or {}).get("subscriptions") or {}).get("sources")), "inbox_path": self.root / "inbox"}
        from paperflow.workspace import load_workspace_settings
        _, settings = load_workspace_settings(self.root)
        ui = read_object(self.root / ".obsidian/plugins/paperflow-automation/data.json")
        source_minutes = int(ui.get("sourceSyncIntervalMinutes", 60))
        if not 1 <= source_minutes <= 1440:
            raise ValueError("subscription interval must be 1..1440 minutes")
        inbox_minutes = int(ui.get("inboxIntervalMinutes", settings.obsidian.inbox_interval_minutes))
        if not 1 <= inbox_minutes <= 1440:
            raise ValueError("Inbox interval must be 1..1440 minutes")
        return {"owner": settings.obsidian.scheduler_owner,
                "daily": settings.obsidian.enable_daily_automation and ui.get("enabled", True),
                "daily_time": ui.get("dailyLocalTime", settings.obsidian.daily_local_time),
                "inbox_minutes": inbox_minutes,
                "source_minutes": source_minutes,
                "inbox_path": self.root / settings.paths.inbox.root,
                "inbox_enabled": ui.get("enabled", True),
                "sources": ui.get("enabled", True) and ui.get("sourceSyncEnabled", True) and any(s.enabled for s in settings.subscriptions.sources)}

    def history(self) -> list[dict[str, Any]]:
        jobs = []
        for path in (state_root(self.root) / "jobs").glob("*.json"):
            try:
                jobs.append(read_object(path))
            except (OSError, ValueError):
                continue
        return jobs

    def tick(self, now: datetime | None = None) -> dict[str, Any]:
        now = (now or datetime.now(BEIJING)).astimezone(BEIJING)
        try:
            policy = self.policy()
            self.status.update(owner=policy["owner"], last_tick_at=now.isoformat(), error=None)
            if policy["owner"] != "core" or not self.service.accepting_jobs:
                return self.status
            with self.service.job_state_lock:
                jobs = self.history()
                runtime = read_object(self.root / ".paperflow/runtime/plugin-state.json") if not standalone(self.root) else {}
                if any(j.get("status") in {"queued", "running", "cancellation-requested"} for j in jobs):
                    return self.status
                last_daily = [timestamp(runtime.get("lastDailyAt"))]
                last_daily += [timestamp(j.get("created_at")) for j in jobs if j.get("kind") == "daily"]
                today_done = any(d and d.date() == now.date() for d in last_daily)
                hour, minute = map(int, policy["daily_time"].split(":"))
                if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                    raise ValueError("daily time must be HH:MM")
                kind = ""
                if policy["daily"] and now.hour * 60 + now.minute >= hour * 60 + minute and not today_done:
                    kind = "daily"
                else:
                    for candidate, interval, enabled, runtime_key in [
                        ("subscription-sync", policy["source_minutes"], policy["sources"], "lastSourceSyncAt"),
                        ("inbox", policy["inbox_minutes"], policy.get("inbox_enabled", True) and not standalone(self.root) and any(policy["inbox_path"].glob("*.md")), "lastInboxAt"),
                    ]:
                        dates = [timestamp(runtime.get(runtime_key))]
                        dates += [timestamp(j.get("created_at")) for j in jobs if j.get("kind") == candidate]
                        last = max((d for d in dates if d), default=None)
                        if enabled and (last is None or now - last >= timedelta(minutes=interval)):
                            kind = candidate
                            break
                if kind:
                    result = self.service.enqueue_scheduled(kind, trigger=f"core-scheduler:{kind}:{now.date().isoformat()}")
                    self.status["last_job_id"] = result["job_id"]
        except Exception as exc:
            self.status["error"] = str(exc)
        return self.status
