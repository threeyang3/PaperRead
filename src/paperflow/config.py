from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ruamel.yaml import YAML

from paperflow.i18n import LocaleInfo, resolve_locale
from paperflow.workspace import (
    WorkspaceSettings,
    load_workspace_settings,
    resolve_vault_root,
)


BEIJING_TZ = ZoneInfo("Asia/Shanghai")

PATH_KEY_TO_RULE = {
    "paper_folder": "note",
    "pdf_folder": "pdf",
    "daily_brief_folder": "daily_brief",
    "request_folder": "inbox",
    "processed_request_folder": "processed_inbox",
    "failed_folder": "failed_inbox",
    "manual_review_folder": "manual_review",
}


@dataclass(frozen=True)
class Config:
    root: Path
    data: dict[str, Any]
    workspace: WorkspaceSettings | None = None

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.data.get(name, {}))

    def path(self, key: str) -> Path:
        legacy_value = self.data.get("vault", {}).get(key)
        if legacy_value:
            return self.root / str(legacy_value)
        if self.workspace and key in PATH_KEY_TO_RULE:
            rule = getattr(self.workspace.paths, PATH_KEY_TO_RULE[key])
            return self.root / rule.root
        raise KeyError(f"Unknown configured path key: {key}")

    @property
    def ui_locale(self) -> LocaleInfo:
        vault = self.data["vault"]
        return resolve_locale(
            self.root,
            configured=str(vault.get("language", "auto")),
            fallback=str(vault.get("language_fallback", "zh-CN")),
        )

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(str(self.data["vault"]["timezone"]))


def _workspace_to_legacy(root: Path, settings: WorkspaceSettings) -> dict[str, Any]:
    full_profile = settings.ai.profiles[settings.ai.full_analysis_profile]
    triage_profile = settings.ai.profiles[settings.ai.triage_profile]
    fallback_provider = ""
    if full_profile.fallback_profile:
        fallback = settings.ai.profiles.get(full_profile.fallback_profile)
        fallback_provider = fallback.provider if fallback else ""
    return {
        "vault": {
            "path": root.as_posix(),
            "timezone": settings.timezone,
            "language": settings.language,
            "language_fallback": settings.language_fallback,
            "paper_folder": settings.paths.note.root,
            "pdf_folder": settings.paths.pdf.root,
            "daily_brief_folder": settings.paths.daily_brief.root,
            "request_folder": settings.paths.inbox.root,
            "processed_request_folder": settings.paths.processed_inbox.root,
            "failed_folder": settings.paths.failed_inbox.root,
            "manual_review_folder": settings.paths.manual_review.root,
        },
        "discovery": settings.discovery.model_dump(mode="json"),
        "arxiv": {
            "request_interval_seconds": settings.downloads.request_interval_seconds,
            "timeout_seconds": settings.downloads.timeout_seconds,
            "max_retries": settings.downloads.max_retries,
            "download_pdf": settings.downloads.enabled,
            "download_source": settings.downloads.source,
            "max_pdf_size_mb": settings.downloads.max_pdf_size_mb,
        },
        "analysis": {
            "provider": full_profile.provider,
            "model": full_profile.model,
            "relevance_provider": triage_profile.provider,
            "relevance_model": triage_profile.model,
            "relevance_prompt_version": "paper-relevance-v1",
            "fallback_provider": fallback_provider or None,
            "language": settings.language_fallback,
            "timeout_seconds": full_profile.timeout_seconds,
            "retry_invalid_output": 1,
            "preserve_raw_output": True,
            "profile": settings.ai.full_analysis_profile,
        },
        "rendering": {
            "filename_strategy": "template",
            "keep_user_sections": True,
            "create_topic_links": True,
            "include_pdf_embed": True,
        },
        "form_flow": {
            "enabled": settings.obsidian.install_form_flow,
            "plugin_id": "form-flow",
            "form_name": "添加论文",
            "processing_mode": "request_file",
            "process_immediately_when_supported": False,
            "inbox_poll_interval_minutes": 5,
        },
        "scheduler": {
            "enabled": False,
            "timezone": settings.timezone,
            "daily_local_time": "08:00",
            "inbox_poll_interval_minutes": 5,
            "process_manual_inbox": True,
            "catch_up_after_missed_run": True,
        },
        "obsidian_automation": {
            "enabled": settings.obsidian.enable_daily_automation,
            "plugin_id": "paperflow-automation",
            "daily_local_time": settings.obsidian.daily_local_time,
            "inbox_poll_interval_minutes": settings.obsidian.inbox_interval_minutes,
            "catch_up_after_missed_run": settings.obsidian.catch_up_after_missed_run,
            "requires_obsidian_open": True,
        },
        "retention": {
            "keep_extracted_text": True,
            "keep_raw_api_responses": True,
            "keep_ai_logs_days": 30,
        },
    }


def load_config(root: Path | None = None) -> Config:
    resolved = resolve_vault_root(root)
    workspace_file = resolved / ".paperflow/workspace.yaml"
    if workspace_file.exists():
        resolved, workspace = load_workspace_settings(resolved)
        return Config(
            root=resolved,
            data=_workspace_to_legacy(resolved, workspace),
            workspace=workspace,
        )

    legacy_file = resolved / "paperflow.yaml"
    if not legacy_file.exists():
        raise FileNotFoundError(
            f"No `.paperflow/workspace.yaml` or legacy `paperflow.yaml` in {resolved}"
        )
    data = YAML(typ="safe").load(legacy_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{legacy_file}: expected a YAML mapping")
    timezone = str(data.get("vault", {}).get("timezone", "UTC"))
    ZoneInfo(timezone)
    data.setdefault("vault", {})["path"] = resolved.as_posix()
    return Config(root=resolved, data=data)


def ensure_layout(cfg: Config) -> None:
    if cfg.workspace:
        roots = [
            rule["root"]
            for rule in cfg.workspace.paths.model_dump(mode="json").values()
        ]
        folders = roots + [
            "20 Topics",
            "30 Reading Notes",
            "90 System/Templates",
            "90 System/Forms",
            "90 System/Taxonomy",
            ".paperflow/migrations/staging",
            ".paperflow/migrations/history",
            ".paperflow/migrations/archive",
        ]
    else:
        folders = [
            "00 Dashboard/Bases",
            "10 Papers/2026",
            "20 Topics",
            "30 Reading Notes",
            "40 Daily Briefs",
            "50 Inbox/Paper Requests",
            "50 Inbox/Processed Requests",
            "50 Inbox/Failed Imports",
            "50 Inbox/Manual Review",
            "80 Attachments/Papers/2026",
            "90 System/Templates",
            "90 System/Forms",
            "90 System/Docs",
            "90 System/Taxonomy",
            ".paperflow/data/papers",
            ".paperflow/cache",
            ".paperflow/state",
            ".paperflow/logs/ai",
            ".paperflow/logs/errors",
            ".paperflow/runtime",
            ".paperflow/scheduler",
        ]
    for folder in dict.fromkeys(folders):
        (cfg.root / folder).mkdir(parents=True, exist_ok=True)
