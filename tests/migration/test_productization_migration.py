from __future__ import annotations

import json
from pathlib import Path

from paperflow.migration_engine import (
    MIGRATION_ID,
    apply,
    build_plan,
    migration_history,
    rollback,
    status,
    verify,
)


def _legacy_record(uid: str = "arxiv:2607.00001") -> dict:
    return {
        "paper_uid": uid,
        "paper_source": "arxiv",
        "paper_arxiv_id": "2607.00001",
        "paper_arxiv_version": 2,
        "paper_title": "Test Paper",
        "paper_authors": ["Ada Lovelace"],
        "paper_pdf_url": "https://arxiv.org/pdf/2607.00001",
        "ai_analysis_status": "complete",
        "ai_analysis_provider": "mock",
        "ai_analysis_model": "deterministic-v1",
        "ai_analysis_prompt_version": "7",
        "ai_summary_short": "Summary",
        "user_priority": 5,
        "user_added_tags": ["keep-me"],
        "system_content_hash": "abc",
        "note_path": "10 Papers/2607.00001.md",
        "future_field": {"must": "survive"},
    }


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "Any Vault"
    legacy = root / ".paperflow/data/papers/arxiv_2607.00001.json"
    legacy.parent.mkdir(parents=True)
    record = _legacy_record()
    legacy.write_text(json.dumps(record), encoding="utf-8")
    note = root / record["note_path"]
    note.parent.mkdir(parents=True)
    note.write_text(
        "<!-- USER_NOTES_START -->\nNever overwrite\n<!-- USER_NOTES_END -->\n",
        encoding="utf-8",
    )
    (root / "paperflow.yaml").write_text(
        "vault:\n"
        "  timezone: Asia/Shanghai\n"
        "  language: zh-CN\n"
        "analysis:\n"
        "  provider: mock\n"
        "  model: deterministic-v1\n"
        "  relevance_provider: mock\n"
        "  relevance_model: deterministic-v1\n"
        "obsidian_automation:\n"
        "  enabled: true\n"
        "  daily_local_time: '07:30'\n",
        encoding="utf-8",
    )
    return root


def test_plan_is_read_only_and_reports_no_network_or_ai(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    plan = build_plan(root)
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }

    assert plan["migration_id"] == MIGRATION_ID
    assert plan["raw_records"] == plan["user_records"] == 1
    assert plan["ai_records"] == 1
    assert plan["unknown_fields"]["arxiv:2607.00001"] == ["future_field"]
    assert plan["network_requests"] == plan["pdf_downloads"] == plan["ai_calls"] == 0
    assert before == after


def test_apply_verify_history_and_rollback_are_reversible(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    legacy = root / ".paperflow/data/papers/arxiv_2607.00001.json"
    legacy_bytes = legacy.read_bytes()
    notes_bytes = (root / "10 Papers/2607.00001.md").read_bytes()

    event = apply(root)
    result = verify(root, event["run_id"])

    assert result["ok"]
    assert result["raw_records"] == 1
    assert result["ai_records"] == 1
    assert result["user_records"] == 1
    raw = json.loads(
        next((root / ".paperflow/data/raw").rglob("*.json")).read_text()
    )
    assert raw["extensions"]["future_field"] == {"must": "survive"}
    user = json.loads(
        next((root / ".paperflow/data/user").glob("*.yaml")).read_text()
    )
    assert user["user"]["user_added_tags"] == ["keep-me"]
    assert legacy.read_bytes() == legacy_bytes
    assert (root / "10 Papers/2607.00001.md").read_bytes() == notes_bytes
    assert status(root)["applied"]
    assert migration_history(root)[-1]["status"] == "applied"
    from paperflow.workspace import load_workspace_settings

    _, settings = load_workspace_settings(root)
    assert settings.ai.profiles["full_analysis"].provider == "mock"
    assert settings.ai.profiles["full_analysis"].model == "deterministic-v1"
    assert settings.obsidian.daily_local_time == "07:30"

    repeated = apply(root)
    assert repeated["status"] == "already-applied"
    assert repeated["changed"] == 0

    rolled_back = rollback(root, event["run_id"])
    assert rolled_back["status"] == "rolled-back"
    assert not (root / ".paperflow/workspace.yaml").exists()
    assert not list((root / ".paperflow/data/raw").rglob("*.json"))
    assert legacy.read_bytes() == legacy_bytes
    assert (root / "10 Papers/2607.00001.md").read_bytes() == notes_bytes


def test_verify_allows_valid_subscription_raw_records(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    apply(root)
    local_raw = next((root / ".paperflow/data/raw").rglob("*.json"))
    subscription_raw = (
        root
        / ".paperflow/data/raw/subscriptions/example/arxiv_2607.00001/v2.json"
    )
    subscription_raw.parent.mkdir(parents=True)
    subscription_raw.write_bytes(local_raw.read_bytes())

    result = verify(root)

    assert result["ok"]
    assert result["raw_records"] == 2
    assert result["migrated_raw_records"] == 1


def test_mid_migration_failure_restores_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    root = _workspace(tmp_path)
    legacy = root / ".paperflow/data/papers/arxiv_2607.00001.json"
    original = legacy.read_bytes()
    import paperflow.migration_engine as engine

    def fail_materialize(*_args, **_kwargs):
        raise RuntimeError("injected staging failure")

    monkeypatch.setattr(engine, "_materialize", fail_materialize)
    import pytest

    with pytest.raises(RuntimeError, match="injected"):
        engine.apply(root)
    assert legacy.read_bytes() == original
    assert not (root / ".paperflow/workspace.yaml").exists()
    assert engine.migration_history(root)[-1]["status"] == "failed-restored"
