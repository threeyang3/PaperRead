from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from paperflow.zotero.core_service import PaperFlowCoreService, read_pairing_token


UID = "arxiv:2607.40001"


def _paper(root: Path) -> None:
    path = root / "data/papers/arxiv_2607.40001.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"paper_uid": UID, "paper_title": "Lifecycle"}),
        encoding="utf-8",
    )


def _job_path(root: Path, job_id: str) -> Path:
    return root / "state/jobs" / f"{job_id}.json"


def test_restart_marks_running_job_interrupted(tmp_path: Path) -> None:
    _paper(tmp_path)
    first = PaperFlowCoreService(tmp_path, port=0)
    queued = first.enqueue_job("analysis", {"paper_uid": UID})
    path = _job_path(tmp_path, queued["job_id"])
    value = json.loads(path.read_text(encoding="utf-8"))
    value["status"] = "running"
    path.write_text(json.dumps(value), encoding="utf-8")

    second = PaperFlowCoreService(tmp_path, port=0)
    second.start()
    try:
        recovered = second.job(queued["job_id"])
        assert recovered["status"] == "interrupted"
        assert recovered["error"] == "Core stopped while this job was running"
    finally:
        second.stop()


def test_duplicate_job_idempotency(tmp_path: Path) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)

    first = service.enqueue_job(
        "analysis",
        {
            "paper_uid": UID,
            "provider": "mock",
            "analysis_profile": "full_analysis",
            "source_content_hash": "pdf-hash",
        },
    )
    second = service.enqueue_job(
        "analysis",
        {
            "paper_uid": UID,
            "provider": "mock",
            "analysis_profile": "full_analysis",
            "source_content_hash": "pdf-hash",
        },
    )

    assert second["job_id"] == first["job_id"]
    assert second["reused"] is True
    assert len(list((tmp_path / "state/jobs").glob("*.json"))) == 1


def test_cancel_queued_job(tmp_path: Path) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    queued = service.enqueue_job("analysis", {"paper_uid": UID})

    cancelled = service.cancel_job(queued["job_id"])

    assert cancelled["status"] == "cancelled"
    assert service.job(queued["job_id"])["status"] == "cancelled"


def test_completed_job_cannot_be_cancelled(tmp_path: Path) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    queued = service.enqueue_job("analysis", {"paper_uid": UID})
    path = _job_path(tmp_path, queued["job_id"])
    value = json.loads(path.read_text(encoding="utf-8"))
    value["status"] = "completed"
    path.write_text(json.dumps(value), encoding="utf-8")

    result = service.cancel_job(queued["job_id"])

    assert result["status"] == "completed"
    assert result["cancelled"] is False


def test_stop_reports_active_job_and_keeps_session_on_timeout(
    tmp_path: Path,
) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    entered = threading.Event()
    release = threading.Event()

    def blocking(job: dict[str, object]) -> None:
        service._update_job_state(str(job["job_id"]), status="running")
        entered.set()
        release.wait(timeout=5)

    service._run_job = blocking  # type: ignore[method-assign]
    service.start()
    queued = service.enqueue_job("analysis", {"paper_uid": UID})
    assert entered.wait(timeout=2)

    result = service.stop(timeout_seconds=0.05)

    assert result["status"] == "stopping"
    assert result["active_job"] == queued["job_id"]
    assert result["process_exit_required"] is True
    assert (tmp_path / "state/zotero-core-session.json").is_file()
    assert read_pairing_token(tmp_path)
    release.set()
    service.worker.join(timeout=2)  # type: ignore[union-attr]
    assert service.stop(timeout_seconds=2)["status"] == "stopped"


def test_cancel_running_job_at_safe_point(tmp_path: Path, monkeypatch) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    entered = threading.Event()

    def fake_analysis(*_args, **_kwargs):
        entered.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if service.active_job_cancel.is_set():
                return {"status": "aborted"}
            time.sleep(0.01)
        raise AssertionError("cancellation was not delivered")

    monkeypatch.setattr(
        "paperflow.zotero.standalone_ai.analyze_standalone",
        fake_analysis,
    )
    service.start()
    try:
        queued = service.enqueue_job("analysis", {"paper_uid": UID})
        assert entered.wait(timeout=2)
        result = service.cancel_job(queued["job_id"])
        assert result["status"] in {"running", "cancelled"}
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if service.job(queued["job_id"])["status"] == "cancelled":
                break
            time.sleep(0.02)
        assert service.job(queued["job_id"])["status"] == "cancelled"
    finally:
        service.stop()


def test_job_state_survives_restart_without_duplicate_worker(tmp_path: Path) -> None:
    _paper(tmp_path)
    first = PaperFlowCoreService(tmp_path, port=0)
    queued = first.enqueue_job("render", {"paper_uid": UID})

    second = PaperFlowCoreService(tmp_path, port=0)
    second.start()
    worker = second.worker
    second._start_worker()
    try:
        assert second.worker is worker
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if second.job(queued["job_id"])["status"] in {
                "completed",
                "skipped",
                "failed",
            }:
                break
            time.sleep(0.02)
        assert second.job(queued["job_id"])["status"] in {
            "completed",
            "skipped",
            "failed",
        }
    finally:
        second.stop()
