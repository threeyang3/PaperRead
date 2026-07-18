from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from paperflow.feed.git_ops import (
    _git,
    feed_git_status,
    normalize_github_repository_url,
)
from paperflow.feed.publisher import build_feed, scan_feed, validate_feed
from paperflow.workspace import WorkspaceSettings


BEIJING = ZoneInfo("Asia/Shanghai")


def auto_publish_feed(
    root: Path,
    settings: WorkspaceSettings,
    *,
    push: bool,
    confirmed_automation: bool,
) -> dict[str, Any]:
    if not confirmed_automation:
        raise ValueError(
            "Automatic publishing requires an explicit persisted authorization"
        )
    publishing = settings.publishing
    if not publishing.enabled:
        return {"status": "disabled", "published": False}
    if not publishing.repository_url:
        raise ValueError("publishing.repository_url is required")
    feed_root = root / ".paperflow/publish/feed"
    status = feed_git_status(feed_root)
    if not status.get("repository"):
        raise ValueError("The public Feed Git repository has not been initialized")
    expected = normalize_github_repository_url(publishing.repository_url)
    if status.get("origin") != expected:
        raise ValueError(
            "Feed origin does not match the configured publishing repository"
        )

    build = build_feed(root, settings, feed_root)
    validation = validate_feed(feed_root)
    findings = scan_feed(feed_root)
    if findings:
        raise RuntimeError(f"Public Feed privacy scan failed: {findings}")
    changes = _git(feed_root, "status", "--porcelain=v1").stdout.splitlines()
    if not changes:
        return {
            "status": "unchanged",
            "published": False,
            "pushed": False,
            "build": build,
            "validation": validation,
        }

    if _git(feed_root, "config", "--get", "user.name", check=False).returncode:
        _git(
            feed_root,
            "config",
            "--local",
            "user.name",
            publishing.publisher_name or "PaperFlow Automation",
        )
    if _git(feed_root, "config", "--get", "user.email", check=False).returncode:
        _git(
            feed_root,
            "config",
            "--local",
            "user.email",
            "paperflow-automation@users.noreply.github.com",
        )
    _git(feed_root, "add", "--all")
    message = (
        "PaperFlow auto publish "
        + datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M %Z")
    )
    commit = _git(feed_root, "commit", "-m", message)
    pushed = False
    if push:
        _git(feed_root, "push", "origin", publishing.branch)
        pushed = True
    return {
        "status": "published" if pushed else "committed",
        "published": True,
        "pushed": pushed,
        "commit": commit.stdout.strip(),
        "build": build,
        "validation": validation,
        "privacy_scan": "passed",
        "origin": expected,
        "branch": publishing.branch,
    }
