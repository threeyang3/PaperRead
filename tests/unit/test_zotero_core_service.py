from __future__ import annotations

import json
import hashlib
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from paperflow.zotero.core_service import PaperFlowCoreService, read_pairing_token
from paperflow.zotero.mapping import apply_links, plan_links


def _request(url: str, *, token: str = "", method: str = "GET", body: dict | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, headers=headers, method=method, data=data)
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_core_service_is_loopback_and_token_protected(tmp_path: Path) -> None:
    paper_dir = tmp_path / ".paperflow/data/papers"
    paper_dir.mkdir(parents=True)
    pdf = b"%PDF-1.7\nPaperFlow test PDF\n%%EOF\n"
    pdf_path = tmp_path / "80 Attachments/Papers/2504.16054.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(pdf)
    (paper_dir / "arxiv_2504.16054.json").write_text(
        json.dumps({
            "paper_uid": "arxiv:2504.16054",
            "paper_title": "π0.5",
            "paper_pdf_path": "80 Attachments/Papers/2504.16054.pdf",
        }),
        encoding="utf-8",
    )
    service = PaperFlowCoreService(tmp_path, port=0)
    result = service.start()
    assert result["network_scope"] == "loopback-only"
    assert service.host == "127.0.0.1"
    assert read_pairing_token(tmp_path) == service.token
    status, health = _request(service.url + "/health")
    assert status == 200 and health["ok"] is True
    with pytest.raises(urllib.error.HTTPError) as error:
        _request(service.url + "/papers/arxiv%3A2504.16054")
    assert error.value.code == 401
    status, paper = _request(service.url + "/papers/arxiv%3A2504.16054", token=service.token)
    assert status == 200 and paper["paper_uid"] == "arxiv:2504.16054"
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(service.url + "/zotero/pdf/arxiv%3A2504.16054", timeout=3)
    assert error.value.code == 401
    pdf_request = urllib.request.Request(
        service.url + "/zotero/pdf/arxiv%3A2504.16054",
        headers={"Authorization": f"Bearer {service.token}"},
    )
    with urllib.request.urlopen(pdf_request, timeout=3) as response:
        assert response.status == 200
        assert response.headers["Content-Type"] == "application/pdf"
        assert response.headers["X-PaperFlow-Sha256"] == hashlib.sha256(pdf).hexdigest()
        assert response.read() == pdf
    status, markdown = _request(
        service.url + "/zotero/markdown/arxiv%3A2504.16054?item_key=ABCD1234",
        token=service.token,
    )
    assert status == 200
    assert markdown["artifact_permission"] == "USER_EDITABLE_PROJECTION"
    assert markdown["content_sha256"] == hashlib.sha256(markdown["content"].encode("utf-8")).hexdigest()
    assert "π0.5" in markdown["content"]
    status, queued = _request(
        service.url + "/analysis/jobs",
        token=service.token,
        method="POST",
        body={"paper_uid": "arxiv:2504.16054"},
    )
    assert status == 202 and queued["status"] == "queued"
    status, job = _request(
        service.url + f"/jobs/{queued['job_id']}",
        token=service.token,
    )
    assert status == 200 and job["job_id"] == queued["job_id"]
    status, jobs = _request(service.url + "/jobs?limit=5", token=service.token)
    assert status == 200 and any(item["job_id"] == queued["job_id"] for item in jobs["jobs"])
    with pytest.raises(ValueError):
        service.enqueue_job("render", {"paper_uid": "arxiv:2504.16054", "target": "unknown"})
    status, subscription = _request(
        service.url + "/subscriptions/sync",
        token=service.token,
        method="POST",
        body={"trigger": "test"},
    )
    assert status == 202 and subscription["status"] == "queued"
    mirrored = service.mirror_annotation({
        "paper_uid": "arxiv:2504.16054",
        "annotation_id": "ANN00001",
        "item_key": "ANN00001",
        "parent_item_key": "ABCD1234",
        "annotation_type": "highlight",
        "text": "A quoted result",
        "comment": "Important",
        "color": "#ffff00",
        "page": "4",
        "position": {"rects": [[1, 2, 3, 4]]},
        "tags": ["evidence"],
    })
    assert mirrored["status"] == "mirrored"
    listed = service.annotation_list("arxiv:2504.16054")
    assert listed["active_count"] == 1
    deleted = service.mirror_annotation({"event": "delete", "annotation_id": "ANN00001"})
    assert deleted["updated"] == 1
    assert service.annotation_list("arxiv:2504.16054")["active_count"] == 0
    status, migration = _request(
        service.url + "/zotero/migration/results",
        token=service.token,
        method="POST",
        body={"items": [{
            "paper_uid": "arxiv:2504.16054",
            "item_key": "ABCD1234",
            "library_id": 1,
            "attachments": [{"key": "ATT00001", "mode": "stored", "sha256": ""}],
        }]},
    )
    assert status == 200 and migration["mappings"]
    inbox = tmp_path / "data/subscriptions/inbox/arxiv_2504.16054.json"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text(json.dumps({
        "schema_version": 1,
        "artifact_permission": "REMOTE_READ_ONLY",
        "paper_uid": "arxiv:2504.16054",
        "title": "π0.5",
        "authors": ["Physical Intelligence"],
        "abstract": "A paper",
        "url": "https://arxiv.org/abs/2504.16054",
        "source_id": "arxiv_2504.16054",
        "feed_id": "ArXiv-data",
        "status": "pending-confirmation",
        "updated_at": "2026-07-24T10:00:00+08:00",
    }, ensure_ascii=False), encoding="utf-8")
    (inbox.parent / "arxiv_2607.00002.json").write_text(json.dumps({
        "schema_version": 1,
        "artifact_permission": "REMOTE_READ_ONLY",
        "paper_uid": "arxiv:2607.00002",
        "title": "Another paper",
        "authors": ["Author"],
        "abstract": "Another paper",
        "url": "https://arxiv.org/abs/2607.00002",
        "source_id": "arxiv_2607.00002",
        "feed_id": "ArXiv-data",
        "status": "imported",
        "updated_at": "2026-07-24T11:00:00+08:00",
    }), encoding="utf-8")
    status, listed = _request(service.url + "/subscriptions/inbox?status=pending-confirmation", token=service.token)
    assert status == 200 and listed["count"] == 1
    assert listed["items"][0]["paper"]["paper_title"] == "π0.5"
    all_subscriptions = service.subscription_inbox(limit=500)
    assert all_subscriptions["count"] == 2
    assert all_subscriptions["counts"] == {"imported": 1, "pending-confirmation": 1}
    status, decision = _request(
        service.url + "/subscriptions/inbox/decision",
        token=service.token,
        method="POST",
        body={"paper_uid": "arxiv:2504.16054", "decision": "imported", "item_key": "ABCD1234"},
    )
    assert status == 200 and decision["status"] == "imported"
    service.stop()
    assert not (tmp_path / ".paperflow/state/zotero-core-session.json").exists()
    assert read_pairing_token(tmp_path) is None


def test_standalone_core_service_does_not_require_vault(tmp_path: Path) -> None:
    (tmp_path / "data/papers").mkdir(parents=True)
    (tmp_path / "data/papers/arxiv_1.json").write_text(
        json.dumps({"paper_uid": "arxiv:1", "paper_title": "Standalone"}),
        encoding="utf-8",
    )
    service = PaperFlowCoreService(tmp_path, port=0)
    service.start()
    mirrored = service.mirror_annotation({
        "paper_uid": "arxiv:1",
        "annotation_id": "ANN00002",
        "item_key": "ANN00002",
        "text": "Core-only annotation",
    })
    assert mirrored["path"].startswith("data/annotations/zotero/")
    assert (tmp_path / "state/zotero-core-session.json").is_file()
    assert not (tmp_path / ".paperflow").exists()
    service.stop()


def test_zotero_pairing_refreshes_random_session_after_restart(tmp_path: Path) -> None:
    (tmp_path / "data/papers").mkdir(parents=True)
    first = PaperFlowCoreService(tmp_path, port=0)
    first.start()
    _, pairing = _request(
        first.url + "/zotero/pairings",
        token=first.token,
        method="POST",
        body={"client_name": "Test Zotero"},
    )
    first_token = first.token
    first.stop()

    second = PaperFlowCoreService(tmp_path, port=0)
    second.start()
    assert second.token != first_token
    status, refreshed = _request(
        second.url + "/zotero/session/refresh",
        method="POST",
        body={
            "pairing_id": pairing["pairing_id"],
            "pairing_secret": pairing["pairing_secret"],
        },
    )
    assert status == 200
    assert refreshed["session_token"] == second.token
    status, jobs = _request(
        second.url + "/jobs",
        token=refreshed["session_token"],
    )
    assert status == 200 and jobs["ok"] is True
    with pytest.raises(urllib.error.HTTPError) as error:
        _request(
            second.url + "/zotero/session/refresh",
            method="POST",
            body={
                "pairing_id": pairing["pairing_id"],
                "pairing_secret": "wrong-secret-value",
            },
        )
    assert error.value.code == 401
    second.stop()


def test_subscription_paper_normalizes_bare_arxiv_source_id() -> None:
    paper = PaperFlowCoreService._subscription_paper({
        "paper_uid": "arxiv:2607.00001",
        "source": "arxiv",
        "source_id": "2607.00001",
        "source_version": 3,
        "title": "A public paper",
        "authors": ["Author"],
    })
    assert paper["paper_source"] == "arxiv"
    assert paper["paper_arxiv_id"] == "2607.00001"
    assert paper["paper_arxiv_version"] == 3


def test_reader_workspace_is_read_only_aggregate(tmp_path: Path) -> None:
    papers = tmp_path / "data/papers"
    papers.mkdir(parents=True)
    (papers / "arxiv_2607.00001.json").write_text(
        json.dumps({"paper_uid": "arxiv:2607.00001", "paper_title": "Reader paper"}),
        encoding="utf-8",
    )
    mapping = tmp_path / "data/connectors/zotero/mappings"
    mapping.mkdir(parents=True)
    (mapping / "arxiv_2607.00001.json").write_text(
        json.dumps({"paper_uid": "arxiv:2607.00001", "zotero": {"item_key": "ABCD1234"}}),
        encoding="utf-8",
    )
    service = PaperFlowCoreService(tmp_path, port=0)
    service.start()
    service.mirror_annotation({
        "paper_uid": "arxiv:2607.00001", "annotation_id": "ANN00001",
        "item_key": "ANN00001", "text": "A quote",
    })
    status, workspace = _request(
        service.url + "/zotero/items/ABCD1234/workspace", token=service.token
    )
    assert status == 200
    assert workspace["linked"] is True
    assert workspace["paper_uid"] == "arxiv:2607.00001"
    assert workspace["annotations"]["active_count"] == 1
    assert workspace["diagnostics"]["permission"] == "read-only-summary"
    assert "path" not in workspace["diagnostics"]
    service.stop()


def test_enqueue_analysis_resolves_profile_to_provider(tmp_path: Path) -> None:
    papers = tmp_path / "data/papers"
    papers.mkdir(parents=True)
    (papers / "arxiv_1.json").write_text(
        json.dumps({"paper_uid": "arxiv:1", "paper_title": "Standalone"}),
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        "analysis:\n  provider: mock\n  profile: configured\n  model: deterministic\n",
        encoding="utf-8",
    )
    service = PaperFlowCoreService(tmp_path, port=0)
    queued = service.enqueue_job(
        "analysis", {"paper_uid": "arxiv:1", "analysis_profile": "configured"}
    )
    record = service.job(queued["job_id"])
    assert record["analysis_profile"] == "configured"
    assert record["provider"] == "mock"
    assert record["model"] == "deterministic"


def test_zotero_event_reuses_matching_canonical_analysis_for_render(tmp_path: Path) -> None:
    digest = "a" * 64
    papers = tmp_path / "data/papers"
    papers.mkdir(parents=True)
    (papers / "arxiv_1.json").write_text(
        json.dumps({
            "paper_uid": "arxiv:1",
            "paper_title": "Analyzed",
            "ai_analysis_status": "complete",
            "ai_analysis_profile": "fallback_analysis",
            "system_content_hash": digest,
        }),
        encoding="utf-8",
    )
    service = PaperFlowCoreService(tmp_path, port=0)
    accepted = service.accept_event({
        "item_key": "ABCD1234",
        "event": "modify",
        "item_type": "regular",
        "is_regular": True,
        "in_collection": True,
        "has_pdf": True,
        "pdf_stable": True,
        "identity_resolved": True,
        "pdf_sha256": digest,
        "paper_uid": "arxiv:1",
        "analysis_profile": "full_analysis",
    })
    assert accepted["pipeline"]["reuse_analysis"] is True
    assert accepted["pipeline"]["queue_render"] is True
    job = service.job(accepted["job"]["job_id"])
    assert job["kind"] == "render"
    assert job["target"] == "zotero"


def test_zotero_public_snapshot_import_and_pdf_staging(tmp_path: Path) -> None:
    (tmp_path / "data/papers").mkdir(parents=True)
    service = PaperFlowCoreService(tmp_path, port=0)
    service.start()
    imported = service.import_paper({
        "paper": {
            "paper_uid": "arxiv:2504.16054",
            "paper_title": "$\\pi_{0.5}$",
            "paper_arxiv_id": "2504.16054",
            "paper_authors": ["Physical Intelligence"],
            "paper_abs_url": "https://arxiv.org/abs/2504.16054",
        }
    })
    assert imported["status"] == "imported"
    pdf = b"%PDF-1.7\nPaperFlow Zotero staging\n%%EOF\n"
    digest = hashlib.sha256(pdf).hexdigest()
    first = service.stage_pdf_chunk(
        "arxiv:2504.16054", pdf[:10], offset="0", total=str(len(pdf)),
        expected_sha256=digest, filename="pi05.pdf", item_key="ABCD1234",
    )
    assert first["status"] == "staging"
    final = service.stage_pdf_chunk(
        "arxiv:2504.16054", pdf[10:], offset="10", total=str(len(pdf)),
        expected_sha256=digest, filename="pi05.pdf", item_key="ABCD1234",
    )
    assert final["status"] == "stored"
    assert (tmp_path / "documents/zotero/arxiv_2504.16054.pdf").read_bytes() == pdf
    record = json.loads((tmp_path / "data/papers/arxiv-2504.16054.json").read_text(encoding="utf-8"))
    assert record["paper_pdf_path"] == "documents/zotero/arxiv_2504.16054.pdf"
    doi = service.import_paper({
        "paper": {"paper_uid": "doi:10.1000/xyz", "paper_title": "DOI paper"}
    })
    assert doi["status"] == "imported"
    assert (tmp_path / "data/papers/doi-10.1000-xyz.json").is_file()
    with pytest.raises(ValueError, match="SHA-256"):
        service.stage_pdf_chunk(
            "arxiv:2504.16054", b"%PDF-bad", offset="0", total="8",
            expected_sha256="0" * 64, filename="bad.pdf",
        )
    service.stop()


def test_core_job_state_survives_service_restart(tmp_path: Path) -> None:
    papers = tmp_path / "data/papers"
    papers.mkdir(parents=True)
    (papers / "arxiv_1.json").write_text(
        json.dumps({"paper_uid": "arxiv:1", "paper_title": "Standalone"}),
        encoding="utf-8",
    )
    first = PaperFlowCoreService(tmp_path, port=0)
    queued = first.enqueue_job("analysis", {"paper_uid": "arxiv:1", "trigger": "test", "target": "zotero"})
    first.start()
    first.jobs.join()
    first.stop()

    second = PaperFlowCoreService(tmp_path, port=0)
    second.start()
    status = second.job(queued["job_id"])
    assert status["status"] == "completed"
    assert status["result"]["analysis"]["status"] in {"written", "reused"}
    assert second.list_jobs()["jobs"][0]["job_id"] == queued["job_id"]
    second.stop()


def test_core_community_publish_requires_confirmation_and_writes_outbox(tmp_path: Path) -> None:
    (tmp_path / "data/papers").mkdir(parents=True)
    service = PaperFlowCoreService(tmp_path, port=0)
    service.start()
    contribution = {
        "contribution_id": "core-publish-1",
        "paper_uid": "arxiv:1",
        "kind": "passage-comment",
        "body": "A reviewed public comment.",
        "tags": ["evidence"],
        "anchor": {
            "pdf_version": 1,
            "pdf_sha256": "a" * 64,
            "page": 1,
            "exact_quote": "A verified quote.",
        },
        "created_at": "2026-07-24T10:00:00+08:00",
    }
    plan = service.community_plan({
        "paper_uid": "arxiv:1",
        "contribution": contribution,
        "creator": "reader",
        "license": "CC-BY-4.0",
    })
    assert plan["status"] == "preview-only"
    with pytest.raises(ValueError, match="confirm=true"):
        service.community_publish({
            "paper_uid": "arxiv:1",
            "contribution": contribution,
            "creator": "reader",
            "license": "CC-BY-4.0",
        })
    result = service.community_publish({
        "paper_uid": "arxiv:1",
        "contribution": contribution,
        "creator": "reader",
        "license": "CC-BY-4.0",
        "confirm": True,
    })
    assert result["status"] == "outbox-written"
    assert result["network_changes"] == 0
    outbox = tmp_path / result["path"]
    assert outbox.is_file()
    from paperflow.community.publisher import verify_content_sha256

    assert verify_content_sha256(json.loads(outbox.read_text(encoding="utf-8")))
    status, routed = _request(
        service.url + "/community/publish",
        token=service.token,
        method="POST",
        body={
            "paper_uid": "arxiv:1",
            "contribution": contribution,
            "creator": "reader",
            "license": "CC-BY-4.0",
            "confirm": True,
        },
    )
    assert status == 200 and routed["status"] == "reused"
    service.stop()


def test_mapping_prefers_exact_arxiv_and_applies_only_exact(tmp_path: Path) -> None:
    papers = tmp_path / ".paperflow/data/papers"
    papers.mkdir(parents=True)
    (papers / "arxiv_2504.16054.json").write_text(
        json.dumps(
            {
                "paper_uid": "arxiv:2504.16054",
                "paper_arxiv_id": "2504.16054",
                "paper_title": "π0.5",
                "paper_authors": ["Physical Intelligence"],
            }
        ),
        encoding="utf-8",
    )
    plan = plan_links(
        tmp_path,
        [
            {
                "key": "ABCD1234",
                "data": {
                    "title": "Different title",
                    "extra": "arXiv:2504.16054",
                    "creators": [{"name": "Someone Else"}],
                },
            }
        ],
    )
    assert plan["plans"][0]["candidate"]["status"] == "exact"
    result = apply_links(tmp_path, plan)
    assert result["mappings"] == [".paperflow/data/connectors/zotero/mappings/arxiv_2504.16054.json"]


def test_mapping_does_not_auto_merge_title_only(tmp_path: Path) -> None:
    papers = tmp_path / ".paperflow/data/papers"
    papers.mkdir(parents=True)
    (papers / "arxiv_2504.16054.json").write_text(
        json.dumps({"paper_uid": "arxiv:2504.16054", "paper_title": "Same title"}),
        encoding="utf-8",
    )
    plan = plan_links(tmp_path, [{"key": "ABCD1234", "data": {"title": "Same title"}}])
    assert plan["plans"][0]["candidate"]["status"] == "manual-review"
