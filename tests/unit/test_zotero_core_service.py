from __future__ import annotations

import json
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
    (paper_dir / "arxiv_2504.16054.json").write_text(
        json.dumps({"paper_uid": "arxiv:2504.16054", "paper_title": "π0.5"}),
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
    status, queued = _request(
        service.url + "/analysis/jobs",
        token=service.token,
        method="POST",
        body={"paper_uid": "arxiv:2504.16054"},
    )
    assert status == 202 and queued["status"] == "queued"
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
    service.stop()
    assert not (tmp_path / ".paperflow/state/zotero-core-session.json").exists()
    assert read_pairing_token(tmp_path) is None


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
