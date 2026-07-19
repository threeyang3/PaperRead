from __future__ import annotations

import json

from paperflow.models import PaperMetadata
from paperflow.pipeline import analyze


def test_analyze_uid_uses_local_metadata_and_assets(tmp_path, monkeypatch) -> None:
    record_dir = tmp_path / ".paperflow/data/papers"
    record_dir.mkdir(parents=True)
    record = {
        "paper_uid": "arxiv:2406.09246",
        "paper_source": "arxiv",
        "paper_arxiv_id": "2406.09246",
        "paper_arxiv_version": 1,
        "paper_title": "OpenVLA",
        "paper_authors": ["Moo Jin Kim"],
        "paper_first_author": "Moo Jin Kim",
        "paper_year": 2024,
        "paper_pdf_url": "https://arxiv.org/pdf/2406.09246",
        "paper_abs_url": "https://arxiv.org/abs/2406.09246",
    }
    (record_dir / "arxiv_2406.09246.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    captured = {}

    def fake_import(cfg, value, **kwargs):
        captured.update({"value": value, **kwargs})
        return {"status": "updated"}

    monkeypatch.setattr(analyze, "import_paper", fake_import)
    cfg = type("Config", (), {"root": tmp_path})()

    assert analyze.analyze_uid(cfg, "arxiv:2406.09246") == {
        "status": "updated"
    }
    assert captured["value"] == record["paper_abs_url"]
    assert isinstance(captured["metadata_override"], PaperMetadata)
    assert captured["reuse_local_assets"] is True
    assert captured["force"] is True
