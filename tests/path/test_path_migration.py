from __future__ import annotations

import json
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from paperflow.paths.migrate import migrate_paths
from paperflow.paths.readable import apply_readable_paper_paths, plan_readable_paper_paths
from paperflow.workspace import WorkspaceSettings, default_workspace_dict
from paperflow.workspace import init_workspace


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


def test_readable_paper_path_migration_is_explicit_and_preserves_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_workspace(tmp_path)
    workspace = tmp_path / ".paperflow/workspace.yaml"
    value = YAML(typ="safe").load(workspace.read_text(encoding="utf-8"))
    value["paths"]["note"]["template"] = "{{year}}/{{paper_id}}.md"
    value["paths"]["paper_hub"]["template"] = "{{year}}/{{paper_id}}.md"
    YAML().dump(value, workspace.open("w", encoding="utf-8", newline="\n"))
    record = {
        "paper_uid": "arxiv:2504.16054",
        "paper_source": "arxiv",
        "paper_arxiv_id": "2504.16054",
        "paper_arxiv_version": 1,
        "paper_title": r"$\pi_{0.5}$: Open-World Generalization",
        "paper_year": 2025,
        "paper_submitted_date": "2025-04-20",
        "note_path": "10 Papers/2025/2504.16054.md",
        "paper_pdf_path": "",
    }
    record_path = tmp_path / ".paperflow/data/papers/arxiv_2504.16054.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record), encoding="utf-8")
    source = tmp_path / record["note_path"]
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "---\npaper_uid: arxiv:2504.16054\n---\n\n"
        "# old\n\n<!-- USER_NOTES_START -->keep<!-- USER_NOTES_END -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "paperflow.pipeline.render.render_uid",
        lambda config, uid: config.root / json.loads(record_path.read_text())["note_path"],
    )
    plan = plan_readable_paper_paths(tmp_path)
    assert plan["move_count"] == 1
    result = apply_readable_paper_paths(tmp_path)
    assert result["status"] == "applied"
    new_paths = list((tmp_path / "10 Papers/2025").glob("*-2504.16054.md"))
    assert len(new_paths) == 1
    new_path = new_paths[0]
    assert "paperflow_redirect" in source.read_text(encoding="utf-8")
    updated = json.loads(record_path.read_text(encoding="utf-8"))
    assert updated["note_path"].endswith("-2504.16054.md")


def test_readable_migration_updates_selected_derived_path(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    workspace = tmp_path / ".paperflow/workspace.yaml"
    value = YAML(typ="safe").load(workspace.read_text(encoding="utf-8"))
    value["paths"]["note"]["template"] = "{{year}}/{{paper_id}}.md"
    value["paths"]["paper_hub"]["template"] = "{{year}}/{{paper_id}}.md"
    YAML().dump(value, workspace.open("w", encoding="utf-8", newline="\n"))
    record = {
        "paper_uid": "arxiv:2504.16054",
        "paper_source": "arxiv",
        "paper_arxiv_id": "2504.16054",
        "paper_arxiv_version": 1,
        "paper_title": "Pi Open World",
        "paper_year": 2025,
        "paper_submitted_date": "2025-04-20",
        "note_path": "10 Papers/2025/2504.16054.md",
        "paper_pdf_path": "",
    }
    papers = tmp_path / ".paperflow/data/papers/arxiv_2504.16054.json"
    papers.parent.mkdir(parents=True, exist_ok=True)
    papers.write_text(json.dumps(record), encoding="utf-8")
    derived = tmp_path / ".paperflow/data/derived/2504.16054.json"
    derived.parent.mkdir(parents=True, exist_ok=True)
    derived.write_text(
        json.dumps({"derived": {"note_path": record["note_path"]}}), encoding="utf-8"
    )
    source = tmp_path / record["note_path"]
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "---\npaper_uid: arxiv:2504.16054\n---\n\n"
        "# old\n\n<!-- USER_NOTES_START -->keep<!-- USER_NOTES_END -->\n",
        encoding="utf-8",
    )

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            "paperflow.pipeline.render.render_uid",
            lambda config, uid: config.root / json.loads(papers.read_text())[
                "note_path"
            ],
        )
        result = apply_readable_paper_paths(tmp_path)
    finally:
        monkeypatch.undo()

    assert result["status"] == "applied"
    updated = json.loads(derived.read_text(encoding="utf-8"))
    assert updated["derived"]["note_path"].endswith("-2504.16054.md")
