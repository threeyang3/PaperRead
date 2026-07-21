from __future__ import annotations

import json
from pathlib import Path

from paperflow.obsidian.frontmatter import read_note
from paperflow.workspace import dump_yaml, default_workspace_dict
from paperflow.workspace_v3 import (
    apply_workspace_v3,
    plan_workspace_v3,
    plan_workspace_v3_rollback,
    rollback_workspace_v3,
)


def test_workspace_v3_dry_run_and_apply_preserve_legacy_pdf(tmp_path: Path) -> None:
    data = default_workspace_dict()
    data["versions"]["workspace"] = 2
    data["versions"]["user"] = 1
    data["versions"]["feed"] = 1
    for key in [
        "annotation_note", "paper_review", "community_note",
        "user_annotations", "community_cache", "community_outbox",
    ]:
        data["paths"].pop(key)
    data.pop("annotations")
    data.pop("community")
    dump_yaml(tmp_path / ".paperflow/workspace.yaml", data)
    dump_yaml(tmp_path / ".paperflow/workspace.local.yaml", {"ai": {"providers": {}}})
    pdf = tmp_path / "80 Attachments/Papers/2026/2607.00001.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\nimmutable")
    note = tmp_path / "10 Papers/2026/arxiv_2607.00001.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "paper_uid: arxiv:2607.00001\n"
        f"paper_pdf_path: {pdf.relative_to(tmp_path).as_posix()}\n"
        "user_reading_status: reading\n"
        "user_custom_flag: keep-me\n"
        "tags: [paper, personal-tag]\n"
        "---\n\n"
        f"PDF: [[{pdf.relative_to(tmp_path).as_posix()}]]\n\n"
        "<!-- USER_NOTES_START -->private note<!-- USER_NOTES_END -->\n",
        encoding="utf-8",
    )
    template = tmp_path / "90 System/Templates/Paper Note Template.md"
    template.parent.mkdir(parents=True)
    template.write_text(
        "# {{ paper_title_display }}\n\n"
        "PDF: [[{{ paper_pdf_path }}]]\n\n"
        "<!-- USER_NOTES_START --><!-- USER_NOTES_END -->\n",
        encoding="utf-8",
    )
    record = {
        "paper_uid": "arxiv:2607.00001",
        "paper_arxiv_id": "2607.00001",
        "paper_arxiv_version": 1,
        "paper_year": 2026,
        "paper_title": "Migration test paper",
        "paper_pdf_path": pdf.relative_to(tmp_path).as_posix(),
        "note_path": note.relative_to(tmp_path).as_posix(),
    }
    record_path = tmp_path / ".paperflow/data/papers/arxiv_2607.00001.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(json.dumps(record), encoding="utf-8")

    plan = plan_workspace_v3(tmp_path)
    assert plan["pdf_copies"] == 1
    assert plan["deletes_old_pdfs"] is False
    result = apply_workspace_v3(tmp_path)

    target = tmp_path / "80 Attachments/Papers/2026/2607.00001/v1.pdf"
    assert target.read_bytes() == pdf.read_bytes()
    assert pdf.exists()
    migrated = json.loads(record_path.read_text(encoding="utf-8"))
    assert migrated["paper_pdf_path"].endswith("/v1.pdf")
    assert result["verification"]["ok"]
    assert result["rendered_notes"] == [note.relative_to(tmp_path).as_posix()]
    frontmatter, body = read_note(note)
    assert frontmatter["paper_pdf_path"] == target.relative_to(tmp_path).as_posix()
    assert frontmatter["user_reading_status"] == "reading"
    assert frontmatter["user_custom_flag"] == "keep-me"
    assert "personal-tag" in frontmatter["tags"]
    assert "private note" in body
    assert f"[[{target.relative_to(tmp_path).as_posix()}]]" in body
    manifest = Path(tmp_path / result["backup"] / "manifest.json")
    assert manifest.exists()
    assert any(item["path"] == ".obsidian" or item["path"].startswith(".obsidian/")
               for item in json.loads(manifest.read_text(encoding="utf-8"))["files"]) is False

    later_user_file = tmp_path / "60 Annotations/later-user-file.annotation.md"
    later_user_file.parent.mkdir(parents=True, exist_ok=True)
    later_user_file.write_text("user-created after migration\n", encoding="utf-8")
    rollback_plan = plan_workspace_v3_rollback(tmp_path, Path(result["backup"]))
    assert rollback_plan["dry_run"] is True
    assert rollback_plan["delete_files"] == []
    rollback = rollback_workspace_v3(tmp_path, Path(result["backup"]))
    assert rollback["deleted"] == 0
    assert later_user_file.read_text(encoding="utf-8") == "user-created after migration\n"
    assert target.exists()
    restored = json.loads(record_path.read_text(encoding="utf-8"))
    assert restored["paper_pdf_path"] == pdf.relative_to(tmp_path).as_posix()
    restored_frontmatter, restored_body = read_note(note)
    assert restored_frontmatter["user_custom_flag"] == "keep-me"
    assert "private note" in restored_body
