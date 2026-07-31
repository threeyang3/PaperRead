from __future__ import annotations

from pathlib import Path

import pytest

from paperflow.security.artifacts import ArtifactPermissionError, PermissionGuard, PublishScanner


def test_system_guard_rejects_user_note_and_allows_core_data(tmp_path: Path) -> None:
    guard = PermissionGuard(tmp_path)
    with pytest.raises(ArtifactPermissionError):
        guard.authorize(tmp_path / "10 Papers/paper.md")
    assert guard.authorize(tmp_path / ".paperflow/data/ai/a.json").name == "a.json"


def test_publish_scanner_rejects_user_files_and_private_suffixes(tmp_path: Path) -> None:
    scanner = PublishScanner(tmp_path)
    findings = scanner.scan([
        tmp_path / "10 Papers/paper.md",
        tmp_path / ".paperflow/data/cache.sqlite",
    ])
    assert {item.reason for item in findings} >= {"user-managed artifact", "forbidden publication suffix"}


def test_explicit_artifact_permissions_cover_core_layers(tmp_path: Path) -> None:
    guard = PermissionGuard(tmp_path)
    assert guard.policy.artifact_permission(tmp_path, tmp_path / "data/raw/arxiv/paper.json") == "IMMUTABLE_SOURCE"
    assert guard.policy.artifact_permission(tmp_path, tmp_path / "data/ai/full/paper.json") == "AI_VERSIONED"
    assert guard.policy.artifact_permission(tmp_path, tmp_path / "data/user/paper.yaml") == "USER_OWNED"
    assert guard.policy.artifact_permission(tmp_path, tmp_path / "documents/zotero/paper.analysis.md") == "USER_EDITABLE_PROJECTION"
    assert guard.policy.artifact_permission(tmp_path, tmp_path / "data/community/subscriptions/paper.json") == "REMOTE_READ_ONLY"
    assert guard.policy.artifact_permission(tmp_path, tmp_path / "runtime/session.token") == "EPHEMERAL"
    assert guard.authorize(tmp_path / "data/ai/full/paper.json", "AI_VERSIONED").name == "paper.json"
    with pytest.raises(ArtifactPermissionError):
        guard.authorize(tmp_path / "data/user/paper.yaml", "AI_VERSIONED")


def test_publish_scanner_rejects_ephemeral_and_remote_cache(tmp_path: Path) -> None:
    scanner = PublishScanner(tmp_path)
    findings = scanner.scan([
        tmp_path / "runtime/session.token",
        tmp_path / "data/subscriptions/inbox.json",
    ])
    assert {item.reason for item in findings} >= {"ephemeral artifact", "remote_read_only artifact"}


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        "state/auth.json",
        ".paperflow/runtime/zotero-core-session.token",
    ],
)
def test_secret_filename_takes_priority_over_parent_directory(
    tmp_path: Path,
    relative: str,
) -> None:
    guard = PermissionGuard(tmp_path)
    path = tmp_path / relative
    assert guard.policy.artifact_permission(tmp_path, path) == "SECRET"
    findings = PublishScanner(tmp_path).scan([path])
    assert "secret artifact" in {item.reason for item in findings}
    with pytest.raises(ArtifactPermissionError):
        guard.authorize(path, "EPHEMERAL")
