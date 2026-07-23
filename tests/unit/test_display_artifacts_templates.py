from __future__ import annotations

import json
from pathlib import Path

import pytest
from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from paperflow.obsidian.artifacts import apply_user_note_migration, plan_user_note_migration
from paperflow.obsidian.view_model import PAPER_VIEW_MODEL_CONTEXT_VERSION, build_paper_view_model
from paperflow.template_sets import TemplateSetManager
from paperflow.text_quality import short_title, title_aliases
from paperflow.workspace import init_workspace, load_workspace_settings
from paperflow.workspace import install_workspace_resources
from paperflow.obsidian.note_renderer import render_paper
from paperflow.obsidian.frontmatter import read_note
from paperflow.validation import validate_all


def _record() -> dict:
    return {
        "paper_uid": "arxiv:2504.16054",
        "paper_arxiv_id": "2504.16054",
        "paper_title": r"$\pi_{0.5}$: a Vision-Language-Action Model",
        "paper_authors": ["Ada Lovelace"],
        "paper_pdf_path": "80 Attachments/Papers/2025/2504.16054/v1.pdf",
        "ai_summary_short": "摘要",
        "ai_recommendation": "建议",
        "ai_novelty_score": 4,
        "ai_novelty_reason": "证据",
        "ai_completeness_score": 4,
        "ai_completeness_reason": "证据",
        "ai_reproducibility_score": 3,
        "ai_reproducibility_reason": "证据",
        "ai_analysis_provider": "mock",
        "ai_analysis_model": "mock",
        "ai_analyzed_at": "2026-07-22T00:00:00+08:00",
        "sections": {},
        "version_change_note": "v1",
        "ai_analysis_prompt_version": "paper-analysis-v3",
    }


def test_short_title_and_aliases_preserve_source_and_user_override():
    record = {**_record(), "paper_display_title": "用户自定义标题", "user_display_title": "用户自定义标题", "aliases": ["我的别名"]}
    assert short_title(record["paper_title"]) == "π₀.₅"
    aliases = title_aliases(record)
    assert record["paper_title"] in aliases
    assert "arXiv 2504.16054" in aliases
    assert "用户自定义标题" in aliases
    assert "我的别名" in aliases


def test_view_model_is_versioned_and_nested(tmp_path: Path):
    init_workspace(tmp_path)
    _, settings = load_workspace_settings(tmp_path)
    model = build_paper_view_model(tmp_path, settings, _record())
    assert model["context_version"] == PAPER_VIEW_MODEL_CONTEXT_VERSION
    assert model["paper"]["display_title"].startswith("π₀.₅")
    assert model["analysis"]["summary_short"] == "摘要"
    assert model["links"]["user_note"].endswith(".notes.md")


def test_user_note_migration_is_dry_run_then_reversible_without_source_loss(tmp_path: Path):
    init_workspace(tmp_path)
    note = tmp_path / "10 Papers/2025/2504.16054.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    original = "---\npaper_uid: arxiv:2504.16054\npaper_arxiv_id: 2504.16054\npaper_title: Test\n---\n\n# Test\n\n<!-- USER_NOTES_START -->\n我的实验想法\n<!-- USER_NOTES_END -->\n"
    note.write_text(original, encoding="utf-8")
    root, settings = load_workspace_settings(tmp_path)
    plan = plan_user_note_migration(root, settings)
    assert plan["count"] == 1
    assert not (tmp_path / "60 User Notes/2025/2504.16054.notes.md").exists()
    result = apply_user_note_migration(root, settings)
    assert result["changed"] == 1
    target = tmp_path / "60 User Notes/2025/2504.16054.notes.md"
    assert target.exists()
    assert "我的实验想法" in target.read_text(encoding="utf-8")
    assert "paperflow-user-note-migrated" in note.read_text(encoding="utf-8")

    # A repeated run may see a previously created target; it must reconcile
    # the Hub marker without replacing the user's target prose.
    note.write_text(original, encoding="utf-8")
    before = target.read_text(encoding="utf-8")
    repeated = apply_user_note_migration(root, settings)
    assert repeated["changed"] == 1
    assert repeated["conflicts"] == []
    assert target.read_text(encoding="utf-8") == before


def test_template_set_listing_and_sandbox(tmp_path: Path):
    init_workspace(tmp_path)
    manager = TemplateSetManager(tmp_path)
    assert {item["id"] for item in manager.list()} == {"academic-zh", "academic-en"}
    assert manager.validate()["ok"]
    env = SandboxedEnvironment(loader=FileSystemLoader(tmp_path), undefined=StrictUndefined)
    with pytest.raises(Exception):
        env.from_string("{{ ''.__class__.__mro__ }}").render()


def test_user_display_title_is_projected_to_hub(tmp_path: Path):
    init_workspace(tmp_path)
    _, settings = load_workspace_settings(tmp_path)
    install_workspace_resources(tmp_path, settings)
    note = tmp_path / "10 Papers/2025/2504.16054.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("---\nuser_display_title: My chosen title\n---\n\n<!-- USER_NOTES_START -->\n<!-- USER_NOTES_END -->\n", encoding="utf-8")
    render_paper(tmp_path, _record(), note)
    frontmatter, body = read_note(note)
    assert frontmatter["title"] == "My chosen title"
    assert "My chosen title" in body


def test_successful_render_clears_stale_manual_review_state(tmp_path: Path):
    init_workspace(tmp_path)
    _, settings = load_workspace_settings(tmp_path)
    install_workspace_resources(tmp_path, settings)
    note = tmp_path / "10 Papers/2025/2504.16054.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "paper_uid: arxiv:2504.16054\n"
        "system_requires_manual_review: true\n"
        "system_error: stale merge review\n"
        "---\n\n"
        "# old hub\n\n"
        "<!-- paperflow-user-note-migrated source=legacy sha256=abc -->\n",
        encoding="utf-8",
    )
    render_paper(
        tmp_path,
        {
            **_record(),
            "system_requires_manual_review": True,
            "system_error": "stale merge review",
        },
        note,
    )
    frontmatter, _ = read_note(note)
    assert frontmatter["system_requires_manual_review"] is False
    assert frontmatter["system_error"] == ""


def test_validation_accepts_migrated_hub_marker(tmp_path: Path):
    init_workspace(tmp_path)
    note = tmp_path / "10 Papers/2025/2504.16054.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "type: paper\n"
        "paper_uid: arxiv:2504.16054\n"
        "user_reading_status: inbox\n"
        "user_learning_status: none\n"
        "user_reproduction_status: none\n"
        "user_added_tags: []\n"
        "paper_authors: []\n"
        "paper_categories: []\n"
        "ai_topics: []\n"
        "ai_method_family: []\n"
        "ai_task_types: []\n"
        "ai_robot_platforms: []\n"
        "ai_datasets: []\n"
        "ai_baselines: []\n"
        "ai_topic_links: []\n"
        "ai_method_links: []\n"
        "ai_dataset_links: []\n"
        "paper_cites: []\n"
        "paper_citation_ids: []\n"
        "ai_related_papers: []\n"
        "paper_has_code: false\n"
        "paper_has_project_page: false\n"
        "paper_has_dataset: false\n"
        "user_favorite: false\n"
        "system_requires_manual_review: false\n"
        "paper_arxiv_version: 1\n"
        "ai_relevance_score: 0\n"
        "ai_novelty_score: 0\n"
        "ai_completeness_score: 0\n"
        "ai_reproducibility_score: 0\n"
        "ai_overall_score: 0\n"
        "user_priority: 3\n"
        "user_rating: 0\n"
        "---\n\n"
        "# Hub\n\n"
        "<!-- paperflow-user-note-migrated source=legacy sha256=abc -->\n",
        encoding="utf-8",
    )
    assert not [error for error in validate_all(tmp_path) if "user note markers" in error]


def test_validation_accepts_legacy_migrated_user_note_link(tmp_path: Path):
    init_workspace(tmp_path)
    user_note = tmp_path / "60 User Notes/2025/2504.16054.notes.md"
    user_note.parent.mkdir(parents=True, exist_ok=True)
    user_note.write_text(
        "---\n"
        "type: paper-user-note\n"
        "paper_uid: arxiv:2504.16054\n"
        "---\n\n# 我的笔记\n",
        encoding="utf-8",
    )
    note = tmp_path / "10 Papers/2025/2504.16054.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "type: paper\n"
        "paper_uid: arxiv:2504.16054\n"
        "user_reading_status: inbox\n"
        "user_learning_status: none\n"
        "user_reproduction_status: none\n"
        "user_added_tags: []\n"
        "paper_authors: []\n"
        "paper_categories: []\n"
        "ai_topics: []\n"
        "ai_method_family: []\n"
        "ai_task_types: []\n"
        "ai_robot_platforms: []\n"
        "ai_datasets: []\n"
        "ai_baselines: []\n"
        "ai_topic_links: []\n"
        "ai_method_links: []\n"
        "ai_dataset_links: []\n"
        "paper_cites: []\n"
        "paper_citation_ids: []\n"
        "ai_related_papers: []\n"
        "paper_has_code: false\n"
        "paper_has_project_page: false\n"
        "paper_has_dataset: false\n"
        "user_favorite: false\n"
        "system_requires_manual_review: false\n"
        "paper_arxiv_version: 1\n"
        "ai_relevance_score: 0\n"
        "ai_novelty_score: 0\n"
        "ai_completeness_score: 0\n"
        "ai_reproducibility_score: 0\n"
        "ai_overall_score: 0\n"
        "user_priority: 3\n"
        "user_rating: 0\n"
        "---\n\n"
        "# Hub\n\n"
        "> 已迁移到 [[60 User Notes/2025/2504.16054.notes]]。\n",
        encoding="utf-8",
    )
    assert not [error for error in validate_all(tmp_path) if "user note markers" in error]


def test_validation_accepts_current_my_notes_link(tmp_path: Path):
    init_workspace(tmp_path)
    user_note = tmp_path / "60 User Notes/2025/2504.16054.notes.md"
    user_note.parent.mkdir(parents=True, exist_ok=True)
    user_note.write_text(
        "---\n"
        "type: paper-user-note\n"
        "paper_uid: arxiv:2504.16054\n"
        "---\n\n# 我的笔记\n",
        encoding="utf-8",
    )
    note = tmp_path / "10 Papers/2025/2504.16054.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "type: paper\n"
        "paper_uid: arxiv:2504.16054\n"
        "user_reading_status: inbox\n"
        "user_learning_status: none\n"
        "user_reproduction_status: none\n"
        "user_added_tags: []\n"
        "paper_authors: []\n"
        "paper_categories: []\n"
        "ai_topics: []\n"
        "ai_method_family: []\n"
        "ai_task_types: []\n"
        "ai_robot_platforms: []\n"
        "ai_datasets: []\n"
        "ai_baselines: []\n"
        "ai_topic_links: []\n"
        "ai_method_links: []\n"
        "ai_dataset_links: []\n"
        "paper_cites: []\n"
        "paper_citation_ids: []\n"
        "ai_related_papers: []\n"
        "paper_has_code: false\n"
        "paper_has_project_page: false\n"
        "paper_has_dataset: false\n"
        "user_favorite: false\n"
        "system_requires_manual_review: false\n"
        "paper_arxiv_version: 1\n"
        "ai_relevance_score: 0\n"
        "ai_novelty_score: 0\n"
        "ai_completeness_score: 0\n"
        "ai_reproducibility_score: 0\n"
        "ai_overall_score: 0\n"
        "user_priority: 3\n"
        "user_rating: 0\n"
        "---\n\n# Hub\n\n- 我的笔记：[[60 User Notes/2025/2504.16054.notes]]\n",
        encoding="utf-8",
    )
    assert not [error for error in validate_all(tmp_path) if "user note markers" in error]


def test_validation_ignores_paper_redirects(tmp_path: Path):
    init_workspace(tmp_path)
    redirect = tmp_path / "10 Papers/2025/2504.16054.md"
    redirect.parent.mkdir(parents=True, exist_ok=True)
    redirect.write_text(
        "---\n"
        "type: paper-redirect\n"
        "paperflow_redirect: true\n"
        "paper_uid: arxiv:2504.16054\n"
        "---\n\n"
        "# Moved\n\n[[10 Papers/2025/π0.5-2504.16054]]\n",
        encoding="utf-8",
    )
    assert not [error for error in validate_all(tmp_path) if str(redirect) in error]
