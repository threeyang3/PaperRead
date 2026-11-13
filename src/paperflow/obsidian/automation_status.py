from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def automation_status(root: Path) -> dict[str, Any] | None:
    settings_path = root / ".obsidian/plugins/paperflow-automation/data.json"
    if not settings_path.is_file():
        return None
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    legacy = settings.get("runtime", {})
    runtime = dict(legacy) if isinstance(legacy, dict) else {}
    source = "legacy-settings"
    error = ""
    runtime_path = root / ".paperflow/runtime/plugin-state.json"
    if runtime_path.is_file():
        try:
            state = json.loads(runtime_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("expected a JSON object")
            runtime.update(state)
            source = "plugin-state"
        except (OSError, ValueError) as exc:
            error = f"Cannot read plugin runtime state: {type(exc).__name__}"
    result = {
        "enabled": settings.get("enabled", False),
        "daily_local_time": settings.get("dailyLocalTime"),
        "inbox_interval_minutes": settings.get("inboxIntervalMinutes"),
        "runtime_source": source,
        "last_daily_at": runtime.get("lastDailyAt"),
        "last_daily_exit_code": runtime.get("lastDailyExitCode"),
        "last_inbox_at": runtime.get("lastInboxAt"),
        "last_inbox_exit_code": runtime.get("lastInboxExitCode"),
        "last_source_sync_at": runtime.get("lastSourceSyncAt"),
        "last_source_sync_exit_code": runtime.get("lastSourceSyncExitCode"),
        "last_update_check_at": runtime.get("lastUpdateCheckAt"),
        "last_update_check_exit_code": runtime.get("lastUpdateCheckExitCode"),
        "active_job": runtime.get("activeJob"),
        "last_message": runtime.get("lastMessage"),
    }
    if error:
        result["runtime_state_error"] = error
    return result
