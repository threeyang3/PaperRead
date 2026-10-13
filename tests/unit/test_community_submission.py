import base64
import json

import httpx
import pytest

from paperflow.community.publisher import build_outbox, immutable_snapshot
from paperflow.community.submission import GitHubSubmission, submission_plan


def selected(root, creator="owner"):
    snapshot = immutable_snapshot({"contribution_id": "selected1", "paper_uid": "arxiv:2504.16054",
                                   "kind": "question", "body": "What supports this conclusion?"},
                                  creator=creator, license_name="CC-BY-4.0")
    build_outbox(root, snapshot, dry_run=False)
    return submission_plan(root, "https://github.com/owner/Feed")


def test_preview_and_hash_confirmation_are_read_only(tmp_path):
    plan = selected(tmp_path)
    calls = []
    with httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(lambda r: calls.append(r))) as client:
        with pytest.raises(ValueError, match="confirmation"):
            GitHubSubmission(client).submit(tmp_path, plan, "incorrect")
    assert calls == [] and plan["network_changes"] == 0 and plan["draft"]
    path = next((tmp_path / ".paperflow/data/community/outbox").rglob("r*.json"))
    path.write_text(path.read_text(encoding="utf-8").replace("What supports", "Changed"), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        submission_plan(tmp_path, "https://github.com/owner/Feed")


def test_owner_identity_and_nested_privacy_fail_closed(tmp_path):
    plan = selected(tmp_path)
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"login": "someone-else"})
    with httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="repository owner"):
            GitHubSubmission(client).submit(tmp_path, plan, plan["plan_sha256"])
    assert calls == ["GET"]
    from paperflow.community.privacy import scan_community_contribution
    assert scan_community_contribution({"extensions": {"user_answer": "private"}})
    assert scan_community_contribution({"anchor": {"prefix": "C:/Users/me/private"}})
    assert scan_community_contribution({"tags": ["token=hidden-secret"]})


def test_creators_cannot_impersonate_repository_owner(tmp_path):
    with pytest.raises(ValueError, match="creator"):
        selected(tmp_path, creator="outsider")


def test_remote_submission_creates_only_draft_branch_and_pr(tmp_path):
    plan = selected(tmp_path)
    mutations = []
    def handler(request):
        path = request.url.path
        if request.method == "GET":
            if path == "/user": return httpx.Response(200, json={"login": "owner"})
            if path == "/repos/owner/Feed": return httpx.Response(200, json={"full_name": "owner/Feed", "default_branch": "main", "permissions": {"push": True}})
            if path.endswith("/git/ref/heads/main"): return httpx.Response(200, json={"object": {"sha": "base"}})
            if path.endswith("/git/commits/base"): return httpx.Response(200, json={"tree": {"sha": "base-tree"}})
            if path.endswith("/contents/checksums/sha256.txt"): return httpx.Response(200, json={"type": "file", "content": ""})
            return httpx.Response(404)
        body = json.loads(request.content)
        mutations.append((path, body))
        if path.endswith("/pulls"): return httpx.Response(201, json={"html_url": "https://github.com/owner/Feed/pull/1"})
        return httpx.Response(201, json={"sha": "created-object"})
    with httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler)) as client:
        result = GitHubSubmission(client).submit(tmp_path, plan, plan["plan_sha256"])
    assert result["status"] == "draft-pr-created"
    assert all(not path.endswith("/git/refs/heads/main") for path, _ in mutations)
    reference = next(body for path, body in mutations if path.endswith("/git/refs"))
    assert reference["ref"] == "refs/heads/" + plan["branch"]
    pull = next(body for path, body in mutations if path.endswith("/pulls"))
    assert pull["draft"] is True and pull["base"] == "main"
    blobs = [base64.b64decode(body["content"]) for path, body in mutations if path.endswith("/git/blobs")]
    assert any(b"What supports" in data for data in blobs)
    assert any(b'"sha256"' in data and b'"path"' in data for data in blobs)
    assert any(b"  manifests/community/arxiv_2504.16054.jsonl" in data for data in blobs)


def test_remote_immutable_revision_conflict_prevents_any_write(tmp_path):
    plan = selected(tmp_path)
    mutations = []
    def handler(request):
        if request.method != "GET": mutations.append(request)
        path = request.url.path
        if path == "/user": return httpx.Response(200, json={"login": "owner"})
        if path == "/repos/owner/Feed": return httpx.Response(200, json={"full_name": "owner/Feed", "default_branch": "main", "permissions": {"push": True}})
        if path.endswith("/git/ref/heads/main"): return httpx.Response(200, json={"object": {"sha": "base"}})
        return httpx.Response(200, json={"type": "file", "content": base64.b64encode(b"different").decode()})
    with httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="immutable"):
            GitHubSubmission(client).submit(tmp_path, plan, plan["plan_sha256"])
    assert mutations == []
