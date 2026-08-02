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


def test_idempotency_distinguishes_zotero_projection_identity(tmp_path: Path) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    common = {
        "paper_uid": UID,
        "provider": "mock",
        "analysis_profile": "full_analysis",
        "source_content_hash": "pdf-hash",
        "target": "zotero",
    }

    first = service.enqueue_job("analysis", {**common, "zotero_item_key": "ITEMA"})
    second = service.enqueue_job("analysis", {**common, "zotero_item_key": "ITEMB"})

    assert second["job_id"] != first["job_id"]
    assert second["reused"] is False


def test_finalize_resolves_cancel_completion_atomically(tmp_path: Path) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    queued = service.enqueue_job("analysis", {"paper_uid": UID})
    service._update_job_state(queued["job_id"], status="running")
    service._update_job_state(queued["job_id"], status="cancellation-requested")

    final = service._finalize_job(
        queued["job_id"], status="completed", result={"projection": "written"}
    )

    assert final["status"] == "completed-after-cancel-request"
    assert final["result"] == {"projection": "written"}


def test_worker_survives_unexpected_job_runner_exception(tmp_path: Path) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    queued = service.enqueue_job("analysis", {"paper_uid": UID})
    job = json.loads(_job_path(tmp_path, queued["job_id"]).read_text(encoding="utf-8"))

    def crash(_job: dict[str, object]) -> None:
        raise RuntimeError("unexpected runner failure")

    service._run_job = crash  # type: ignore[method-assign]
    service.jobs.put(job)
    service._start_worker()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and service.jobs.unfinished_tasks:
            time.sleep(0.02)
        assert service.worker is not None
        assert service.worker.is_alive()
    finally:
        service.worker_stop.set()
        if service.worker is not None:
            service.worker.join(timeout=2)


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


def test_stop_during_cancellation_preserves_honest_state(tmp_path: Path) -> None:
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
    requested = service.cancel_job(queued["job_id"])
    assert requested["status"] == "cancellation-requested"

    result = service.stop(timeout_seconds=0.05)

    assert result["status"] == "stopping"
    assert result["active_job"] == queued["job_id"]
    assert result["process_exit_required"] is True
    assert service.job(queued["job_id"])["status"] == "cancellation-requested"
    assert service.worker is not None and service.worker.is_alive()
    assert (tmp_path / "state/zotero-core-session.json").is_file()
    release.set()
    service.worker.join(timeout=2)
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
        assert result["status"] in {"cancellation-requested", "cancelled"}
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if service.job(queued["job_id"])["status"] == "cancelled":
                break
            time.sleep(0.02)
        assert service.job(queued["job_id"])["status"] == "cancelled"
    finally:
        service.stop()


def test_running_non_cancelable_operation_is_not_reported_as_cancelled(
    tmp_path: Path, monkeypatch
) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    entered = threading.Event()
    release = threading.Event()

    def non_cancelable(*_args, **_kwargs):
        entered.set()
        release.wait(timeout=3)
        return {"status": "written", "side_effect": True}

    monkeypatch.setattr("paperflow.zotero.standalone_ai.analyze_standalone", non_cancelable)
    service.start()
    try:
        queued = service.enqueue_job("analysis", {"paper_uid": UID})
        assert entered.wait(timeout=2)
        requested = service.cancel_job(queued["job_id"])
        assert requested["status"] == "cancellation-requested"
        release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = service.job(queued["job_id"])
            if state["status"] == "completed-after-cancel-request":
                break
            time.sleep(0.02)
        assert service.job(queued["job_id"])["status"] == "completed-after-cancel-request"
    finally:
        release.set()
        service.stop()


def test_cancel_request_timestamp_is_persisted(tmp_path: Path, monkeypatch) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    entered = threading.Event()
    release = threading.Event()

    def blocking(*_args, **_kwargs):
        entered.set()
        release.wait(timeout=3)
        return {"status": "written"}

    monkeypatch.setattr("paperflow.zotero.standalone_ai.analyze_standalone", blocking)
    service.start()
    try:
        queued = service.enqueue_job("analysis", {"paper_uid": UID})
        assert entered.wait(timeout=2)
        service.cancel_job(queued["job_id"])
        state = json.loads(_job_path(tmp_path, queued["job_id"]).read_text(encoding="utf-8"))
        assert state["status"] == "cancellation-requested"
        assert state["cancellation_requested_at"]
    finally:
        release.set()
        service.stop()


def test_cancelled_job_is_not_requeued_after_restart(tmp_path: Path) -> None:
    _paper(tmp_path)
    first = PaperFlowCoreService(tmp_path, port=0)
    queued = first.enqueue_job("analysis", {"paper_uid": UID})
    first.cancel_job(queued["job_id"])

    second = PaperFlowCoreService(tmp_path, port=0)
    second.start()
    try:
        time.sleep(0.1)
        assert second.job(queued["job_id"])["status"] == "cancelled"
        assert second.jobs.empty()
    finally:
        second.stop()


def test_cancelled_analysis_does_not_write_ai_record(tmp_path: Path) -> None:
    _paper(tmp_path)
    service = PaperFlowCoreService(tmp_path, port=0)
    queued = service.enqueue_job("analysis", {"paper_uid": UID})
    service.cancel_job(queued["job_id"])

    service.start()
    try:
        time.sleep(0.1)
        assert service.job(queued["job_id"])["status"] == "cancelled"
        assert not (tmp_path / "data/ai").exists()
    finally:
        service.stop()


def test_cancelled_render_does_not_replace_note(tmp_path: Path) -> None:
    _paper(tmp_path)
    note = tmp_path / "documents/zotero/arxiv_2607.40001.analysis.md"
    note.parent.mkdir(parents=True)
    note.write_text("user-owned marker", encoding="utf-8")
    service = PaperFlowCoreService(tmp_path, port=0)
    queued = service.enqueue_job("render", {"paper_uid": UID, "target": "zotero"})
    service.cancel_job(queued["job_id"])

    service.start()
    try:
        time.sleep(0.1)
        assert service.job(queued["job_id"])["status"] == "cancelled"
        assert note.read_text(encoding="utf-8") == "user-owned marker"
    finally:
        service.stop()


def test_cancelled_subscription_sync_stops_before_next_source(tmp_path: Path, monkeypatch) -> None:
    _paper(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "subscriptions:\n"
        "  sources:\n"
        "    - name: first\n      url: https://first.invalid/feed\n"
        "    - name: second\n      url: https://second.invalid/feed\n",
        encoding="utf-8",
    )
    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def fake_sync(_root: Path, *, name: str, **_kwargs):
        calls.append(name)
        entered.set()
        release.wait(timeout=3)
        return {"name": name, "created": 1}

    monkeypatch.setattr("paperflow.zotero.standalone_sync.sync_core_feed", fake_sync)
    service = PaperFlowCoreService(tmp_path, port=0)
    service.start()
    try:
        queued = service.subscription_sync({"trigger": "test"})
        assert entered.wait(timeout=2)
        service.cancel_job(queued["job_id"])
        release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if service.job(queued["job_id"])["status"] == "completed-after-cancel-request":
                break
            time.sleep(0.02)
        assert calls == ["first"]
        assert service.job(queued["job_id"])["status"] == "completed-after-cancel-request"
    finally:
        release.set()
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
