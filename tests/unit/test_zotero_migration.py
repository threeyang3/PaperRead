from __future__ import annotations

import json
from pathlib import Path

from paperflow.zotero.migration import ingest_plugin_results, plan_migration, verify_migration


def _workspace(tmp_path: Path) -> None:
    record_dir = tmp_path / ".paperflow/data/papers"
    record_dir.mkdir(parents=True)
    pdf = tmp_path / "80 Attachments/Papers/2025/p.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"pdf")
    (record_dir / "arxiv_2504.16054.json").write_text(
        json.dumps(
            {
                "paper_uid": "arxiv:2504.16054",
                "paper_arxiv_id": "2504.16054",
                "paper_title": "π0.5",
                "paper_pdf_path": "80 Attachments/Papers/2025/p.pdf",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_plan_contains_pdf_hash_and_never_writes_mapping(tmp_path: Path) -> None:
    _workspace(tmp_path)
    plan = plan_migration(
        tmp_path,
        [{"key": "ABCD1234", "data": {"title": "π0.5", "extra": "arXiv:2504.16054"}}],
    )
    item = plan["papers"][0]
    assert item["item_action"] == "reuse"
    assert item["attachment"]["sha256"]
    assert not (tmp_path / ".paperflow/data/connectors/zotero/mappings").exists()


def test_ingest_results_and_verify(tmp_path: Path) -> None:
    result = ingest_plugin_results(
        tmp_path,
        {"items": [{"paper_uid": "arxiv:2504.16054", "item_key": "ABCD1234", "library_id": 1}]},
    )
    assert result["status"] == "applied"
    verified = verify_migration(tmp_path)
    assert verified == {"ok": True, "checked": 1, "valid": 1, "issues": []}
