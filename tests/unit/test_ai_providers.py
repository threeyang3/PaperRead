from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperflow.ai.codex_runtime import isolated_codex_environment
from paperflow.ai.codex_adapter import reasoning_effort_args
from paperflow.ai.providers import (
    MockProvider,
    explain_profile,
    validate_extra_args,
)
from paperflow.data.records import AnalysisIdentity
from paperflow.workspace import (
    AIProfile,
    ProviderConfig,
    default_workspace_dict,
    WorkspaceSettings,
)


def test_codex_runtime_never_reads_or_copies_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "codex-home"
    home.mkdir()
    auth = home / "auth.json"
    auth.write_text('{"secret":"do-not-copy"}', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    staged = tmp_path / "staged"

    environment = isolated_codex_environment(staged)

    assert environment["CODEX_HOME"] == str(home)
    assert not list(staged.rglob("auth.json"))
    assert auth.read_text(encoding="utf-8") == '{"secret":"do-not-copy"}'


def test_extra_args_allowlist_blocks_privilege_escalation() -> None:
    assert validate_extra_args("codex", ["--ephemeral"]) == ["--ephemeral"]
    with pytest.raises(ValueError, match="Dangerous"):
        validate_extra_args("codex", ["--dangerously-bypass-approvals"])
    with pytest.raises(ValueError, match="Unsupported"):
        validate_extra_args("claude", ["--unknown-flag"])


def test_codex_reasoning_effort_is_a_bounded_config_override() -> None:
    assert reasoning_effort_args("") == []
    assert reasoning_effort_args("high") == [
        "--config",
        'model_reasoning_effort="high"',
    ]
    with pytest.raises(ValueError, match="reasoning effort"):
        reasoning_effort_args("unlimited")


def test_mock_provider_capability_and_profile_selection(tmp_path: Path) -> None:
    settings = WorkspaceSettings.model_validate(default_workspace_dict())
    report = MockProvider(
        tmp_path, settings.ai.providers["mock"]
    ).check_available()
    selection = explain_profile(
        "full_analysis", settings.ai.profiles, settings.ai.providers
    )
    assert report.available
    assert selection["provider"] == "codex"
    assert selection["model"] == "<cli-default>"


def test_analysis_identity_is_stable_and_complete() -> None:
    identity = AnalysisIdentity(
        provider="codex",
        model="gpt-example",
        profile="full_analysis",
        prompt_version="paper-analysis-v3",
        analysis_schema_version=1,
        source_content_hash="abc",
    )
    assert identity.analysis_id == identity.analysis_id
    changed = identity.model_copy(update={"model": "different"})
    assert changed.analysis_id != identity.analysis_id
