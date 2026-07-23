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
