from __future__ import annotations

import json
from pathlib import Path

import pytest

import paperflow.application.paper_service as service_module
from paperflow.application import (
    AddPaperRequest,
    OperationResult,
    PaperApplicationService,
)
from paperflow.workspace import init_workspace


def _service(tmp_path: Path) -> PaperApplicationService:
    vault = tmp_path / "vault"
    init_workspace(vault)
    return PaperApplicationService(vault)


def test_service_add_uses_explicit_application_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    captured: dict = {}

    def fake_import(_cfg, source: str, **kwargs):
        captured.update({"source": source, **kwargs})
        return {
            "status": "imported",
            "paper_uid": "arxiv:2601.10001",
            "note_path": "10 Papers/2026/service.md",
        }

    monkeypatch.setattr(service_module, "import_paper", fake_import)
    result = service.add(
        AddPaperRequest(
            source="2601.10001",
            priority=5,
            favorite=True,
            queued=True,
            user_tags=("service", "form-flow"),
            topic_hint="Tactile Sensing",
            user_note="service note",
            source_request_id="service-request",
            import_method="form-flow",
        )
    )

    assert isinstance(result, OperationResult)
    assert result.status == "imported"
    assert result.paper_uid == "arxiv:2601.10001"
    assert result.artifacts["note_path"] == "10 Papers/2026/service.md"
    assert captured["source"] == "2601.10001"
    assert captured["user_intent"].user_values() == {
        "user_priority": 5,
        "user_favorite": True,
        "user_reading_status": "queued",
        "user_added_tags": ["service", "form-flow"],
    }
    assert captured["topic"] == "Tactile Sensing"


def test_service_duplicate_add_refreshes_only_user_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    uid = "arxiv:2601.10004"
    refreshed: dict[str, object] = {}

    monkeypatch.setattr(
        service_module,
        "import_paper",
        lambda *_args, **_kwargs: {
            "status": "skipped",
            "paper_uid": uid,
            "note_path": "10 Papers/2026/duplicate.md",
        },
    )

    def fake_refresh(paper_uid: str, intent) -> bool:
        refreshed["paper_uid"] = paper_uid
        refreshed["user"] = intent.user_values()
        return True

    monkeypatch.setattr(service, "_refresh_user_projection", fake_refresh)
    result = service.add(
        AddPaperRequest(
            source="2601.10004",
            priority=5,
            favorite=True,
            queued=True,
            user_tags=("projection-fresh",),
            source_request_id="duplicate-request",
            import_method="form-flow",
        )
    )

    assert result.status == "skipped"
    assert result.artifacts["system_work"] == "skipped"
    assert result.artifacts["user_state_updated"] is True
    assert result.artifacts["projection_refreshed"] is True
    assert refreshed == {
        "paper_uid": uid,
        "user": {
            "user_priority": 5,
            "user_favorite": True,
            "user_reading_status": "queued",
            "user_added_tags": ["projection-fresh"],
        },
    }


def test_service_contract_covers_analyze_refresh_render_and_inspect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    uid = "arxiv:2601.10002"
    record_path = service.config.root / ".paperflow/data/papers/arxiv_2601.10002.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(
            {
                "paper_uid": uid,
                "paper_abs_url": "https://arxiv.org/abs/2601.10002",
                "paper_title": "Service contract fixture",
                "paper_arxiv_id": "2601.10002",
                "paper_arxiv_version": 1,
                "paper_pdf_path": "",
                "note_path": "",
                "layer_paths": {},
                "ai_analysis_status": "pending",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        service_module,
        "analyze_uid",
        lambda *_args: {"status": "updated", "paper_uid": uid},
    )
    monkeypatch.setattr(
        service_module,
        "import_paper",
        lambda *_args, **_kwargs: {"status": "updated", "paper_uid": uid},
    )
    rendered = service.config.root / "10 Papers/2026/service-contract.md"
    monkeypatch.setattr(service_module, "render_uid", lambda *_args: rendered)

    assert service.analyze(uid).status == "updated"
    assert service.refresh(uid).status == "updated"
    assert service.render(uid).artifacts["note_path"] == str(rendered)
    assert service.inspect(uid)["exists"] is True
    assert service.inspect("arxiv:missing") == {
        "paper_uid": "arxiv:missing",
        "exists": False,
    }


def test_service_does_not_hide_retryable_analysis_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(
        service_module,
        "analyze_uid",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("retryable failure")),
    )

    with pytest.raises(RuntimeError, match="retryable failure"):
        service.analyze("arxiv:2601.10003")
