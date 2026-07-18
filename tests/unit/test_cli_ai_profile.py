from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.workspace import init_workspace, load_workspace_settings


def test_noninteractive_ai_profile_update_is_atomic(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    init_workspace(vault)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "ai",
            "set-profile",
            "full_analysis",
            "--provider",
            "mock",
            "--model",
            "deterministic-v1",
            "--timeout",
            "90",
            "--reasoning-effort",
            "medium",
            "--no-fallback",
            "--no-reuse-feed",
            "--reanalyze-when",
            "never",
            "--vault",
            str(vault),
        ],
    )

    assert result.exit_code == 0, result.output
    _, settings = load_workspace_settings(vault)
    profile = settings.ai.profiles["full_analysis"]
    assert profile.provider == "mock"
    assert profile.model == "deterministic-v1"
    assert profile.timeout_seconds == 90
    assert profile.reasoning_effort == "medium"
    assert profile.fallback_profile == ""
    assert profile.reuse_feed_analysis is False
    assert profile.reanalyze_when == "never"

    local = vault / ".paperflow/workspace.local.yaml"
    before = local.read_bytes()
    rejected = runner.invoke(
        app,
        [
            "ai",
            "set-profile",
            "full_analysis",
            "--provider",
            "unknown",
            "--vault",
            str(vault),
        ],
    )
    assert rejected.exit_code != 0
    assert local.read_bytes() == before
