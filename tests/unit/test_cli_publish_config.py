from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.workspace import init_workspace, load_workspace_settings


def test_noninteractive_publish_configuration_is_atomic(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    init_workspace(vault)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "publish",
            "configure",
            "--feed-id",
            "robotics-feed",
            "--name",
            "Robotics Reading Feed",
            "--publisher-name",
            "Example Publisher",
            "--publisher-url",
            "https://example.org/paperflow",
            "--data-license",
            "USER-SELECTED-LICENSE",
            "--repository-url",
            "https://github.com/example/robotics-feed",
            "--branch",
            "main",
            "--vault",
            str(vault),
        ],
    )

    assert result.exit_code == 0, result.output
    _, settings = load_workspace_settings(vault)
    publishing = settings.publishing
    assert publishing.enabled
    assert publishing.feed_id == "robotics-feed"
    assert publishing.data_license == "USER-SELECTED-LICENSE"
    assert (
        publishing.repository_url
        == "https://github.com/example/robotics-feed.git"
    )
    assert publishing.include_pdf_files is False
    assert publishing.pdf_policy == "link-only"

    local = vault / ".paperflow/workspace.local.yaml"
    before = local.read_bytes()
    rejected = runner.invoke(
        app,
        [
            "publish",
            "configure",
            "--feed-id",
            "../escape",
            "--name",
            "Bad",
            "--publisher-name",
            "Bad",
            "--data-license",
            "Bad",
            "--vault",
            str(vault),
        ],
    )
    assert rejected.exit_code != 0
    assert local.read_bytes() == before
