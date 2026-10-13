from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from paperflow.workspace import default_workspace_dict, dump_yaml
from paperflow.workspace_v3 import verify_workspace_v3


@pytest.mark.parametrize(
    ("link", "valid"),
    [
        ("v1.pdf", True),
        ("v1", True),
        ("v1#page=2|PDF", True),
        ("v1.pdf#page=2|PDF", True),
        ("v10.pdf", False),
        ("v1.pdf.bak", False),
        ("v2", False),
    ],
)
def test_pdf_wikilinks_match_exact_version(tmp_path: Path, link: str, valid: bool):
    dump_yaml(tmp_path / ".paperflow/workspace.yaml", default_workspace_dict())
    relative = "80 Attachments/Papers/2026/2607.00001/v1.pdf"
    pdf = tmp_path / relative
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\nfixture")
    note_relative = "10 Papers/2026/test.md"
    note = tmp_path / note_relative
    note.parent.mkdir(parents=True)
    note.write_text(
        f"---\npaper_pdf_path: {relative}\n---\n"
        f"PDF: [[{pdf.parent.relative_to(tmp_path).as_posix()}/{link}]]\n",
        encoding="utf-8",
    )
    record = tmp_path / ".paperflow/data/papers/arxiv_2607.00001.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({
        "paper_uid": "arxiv:2607.00001",
        "paper_pdf_path": relative,
        "note_path": note_relative,
    }), encoding="utf-8")
    index = tmp_path / ".paperflow/data/derived/pdf-index/arxiv_2607.00001.json"
    index.parent.mkdir(parents=True)
    index.write_text(json.dumps({"versions": [{
        "path": relative, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
    }]}), encoding="utf-8")
    result = verify_workspace_v3(tmp_path)
    assert result["note_link_mismatches"] == ([] if valid else [note_relative])
