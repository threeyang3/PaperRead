import json
from pathlib import Path

import pytest

from paperflow.zotero.core_service import PaperFlowCoreService
from paperflow.zotero.store import state_root


def test_retry_legacy_failure_uses_current_identity_and_preserves_history(tmp_path: Path):
    papers = tmp_path / ".paperflow/data/papers"
    papers.mkdir(parents=True)
    (papers / "arxiv_2504.16054.json").write_text(json.dumps({"paper_uid": "arxiv:2504.16054"}), encoding="utf-8")
    service = PaperFlowCoreService(tmp_path, port=0)
    old = service.enqueue_job("render", {"paper_uid": "arxiv:2504.16054v1", "source_content_hash": "old-machine-hash"})
    service._update_job_state(old["job_id"], status="running")
    service._finalize_job(old["job_id"], status="failed", result={}, error="old computer missing path")
    path = state_root(tmp_path) / "jobs" / f'{old["job_id"]}.json'
    before = path.read_bytes()
    new = service.retry_job(old["job_id"])
    job = service.job(new["job_id"])
    assert job["paper_uid"] == "arxiv:2504.16054"
    assert job["source_content_hash"] == ""
    assert job["retry_of"] == old["job_id"]
    assert path.read_bytes() == before
    assert service.retry_job(old["job_id"])["job_id"] == new["job_id"]


def test_active_and_unknown_history_cannot_be_retried(tmp_path: Path):
    service = PaperFlowCoreService(tmp_path, port=0)
    active = service.enqueue_scheduled("daily", trigger="test")
    with pytest.raises(ValueError, match="only failed"):
        service.retry_job(active["job_id"])
    service._update_job_state(active["job_id"], status="cancelled")
    service._update_job_state(active["job_id"], kind="shell", command="malicious")
    with pytest.raises(ValueError, match="unsupported"):
        service.retry_job(active["job_id"])
    assert len(service.list_jobs()["jobs"]) == 1


def test_retry_missing_paper_and_stopping_core_rejected(tmp_path: Path):
    service = PaperFlowCoreService(tmp_path, port=0)
    old = service.enqueue_job("render", {"paper_uid": "arxiv:2504.16054"})
    service._update_job_state(old["job_id"], status="cancelled")
    with pytest.raises(ValueError, match="canonical paper"):
        service.retry_job(old["job_id"])
    service.accepting_jobs = False
    with pytest.raises(ValueError, match="stopping"):
        service.retry_job(old["job_id"])
