from __future__ import annotations

from pathlib import Path

from paperflow.data.store import persist_layer_records
from paperflow.zotero.core_service import PaperFlowCoreService


def test_reader_finds_analysis_from_canonical_storage(tmp_path: Path) -> None:
    result = persist_layer_records(tmp_path, {
        "paper_uid": "arxiv:2504.16054",
        "paper_arxiv_id": "2504.16054",
        "paper_arxiv_version": 1,
        "paper_title": "Example paper",
        "system_content_hash": "abc123",
        "ai_analysis_status": "complete",
        "ai_analysis_provider": "mock",
        "ai_analysis_model": "deterministic-v1",
        "ai_analysis_profile": "full_analysis",
        "ai_summary_short": "Persisted explanation",
    })
    assert "/2504.16054/" in result["ai"]
    service = PaperFlowCoreService(tmp_path, port=0)
    summary = service._analysis_summary("arxiv:2504.16054")
    assert summary["status"] == "complete"
    assert summary["summary"]["ai_summary_short"] == "Persisted explanation"
