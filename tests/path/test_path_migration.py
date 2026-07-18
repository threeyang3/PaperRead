from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperflow.paths.migrate import migrate_paths
from paperflow.workspace import WorkspaceSettings, default_workspace_dict


def test_path_migration_creates_note_redirect_and_updates_pdf_link(
    tmp_path: Path,
) -> None:
    data = default_workspace_dict()
    data["paths"]["note"] = {
        "root": "Library",
        "template": "{{year}}/{{paper_id}}.md",
    }
    data["paths"]["pdf"] = {
        "root": "Files",
        "template": "{{year}}/{{paper_id}}.pdf",
    }
    settings = WorkspaceSettings.model_validate(data)
    record = {
        "paper_uid": "arxiv:2607.00001",
        "paper_source": "arxiv",
        "paper_arxiv_id": "2607.00001",
        "paper_arxiv_version": 1,
        "paper_year": 2026,
        "paper_submitted_date": "2026-07-01",
        "note_path": "Old/Paper.md",
        "paper_pdf_path": "Old/Paper.pdf",
    }
    legacy = tmp_path / ".paperflow/data/papers/arxiv_2607.00001.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps(record), encoding="utf-8")
    note = tmp_path / record["note_path"]
    pdf = tmp_path / record["paper_pdf_path"]
    note.parent.mkdir(parents=True)
    note.write_text(
        "<!-- USER_NOTES_START -->keep<!-- USER_NOTES_END -->\n"
        "![[Old/Paper.pdf]]",
        encoding="utf-8",
    )
    pdf.write_bytes(b"%PDF-1.7 test")

    dry = migrate_paths(tmp_path, settings, dry_run=True)
    assert dry["move_count"] == 2
    assert dry["redirect_count"] == 1

    result = migrate_paths(tmp_path, settings, dry_run=False)
    new_note = tmp_path / "Library/2026/2607.00001.md"
    new_pdf = tmp_path / "Files/2026/2607.00001.pdf"
    assert result["applied"] == 2
    assert new_note.exists() and new_pdf.exists()
    assert "USER_NOTES_START -->keep" in new_note.read_text(encoding="utf-8")
    assert "Files/2026/2607.00001.pdf" in new_note.read_text(encoding="utf-8")
    assert "type: paper-redirect" in note.read_text(encoding="utf-8")
    assert not pdf.exists()


def test_path_migration_refuses_existing_target(tmp_path: Path) -> None:
    data = default_workspace_dict()
    data["path_templates"]["collision_policy"] = "error"
    data["paths"]["note"] = {
        "root": "Library",
        "template": "{{type|slug}}/{{title|slug}}.md",
    }
    settings = WorkspaceSettings.model_validate(data)
    record = {
        "paper_uid": "arxiv:2607.00002",
        "paper_source": "arxiv",
        "paper_arxiv_id": "2607.00002",
        "paper_arxiv_version": 1,
        "paper_title": "Same Title",
        "paper_type": "Paper",
        "note_path": "Old/Second.md",
        "paper_pdf_path": "",
    }
    legacy = tmp_path / ".paperflow/data/papers/arxiv_2607.00002.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps(record), encoding="utf-8")
    source = tmp_path / record["note_path"]
    source.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    target = tmp_path / "Library/Paper/Same-Title.md"
    target.parent.mkdir(parents=True)
    target.write_text("existing", encoding="utf-8")

    plan = migrate_paths(tmp_path, settings, dry_run=True)
    assert plan["conflicts"]
    with pytest.raises(RuntimeError, match="conflicts"):
        migrate_paths(tmp_path, settings, dry_run=False)
    assert source.read_text(encoding="utf-8") == "source"
    assert target.read_text(encoding="utf-8") == "existing"
