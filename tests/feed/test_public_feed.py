from __future__ import annotations

import json
import shutil
import tarfile
from pathlib import Path

import pytest
import respx
import httpx
import zstandard

from paperflow.data.records import (
    AIAnalysisRecord,
    AnalysisIdentity,
    RawPaperRecord,
    UserPaperRecord,
)
from paperflow.feed import (
    auto_publish_feed,
    build_feed,
    create_snapshot,
    feed_git_status,
    init_feed_repository,
    scan_feed,
    sync_feed,
    validate_feed,
)
from paperflow.feed.git_ops import normalize_github_repository_url
from paperflow.feed.subscriber import _download_linked_pdf
from paperflow.community.publisher import build_outbox, immutable_snapshot
from paperflow.zotero.standalone_sync import sync_core_feed
from paperflow.workspace import (
    WorkspaceSettings,
    default_workspace_dict,
    init_workspace,
    install_workspace_resources,
    load_workspace_settings,
)


def _settings() -> WorkspaceSettings:
    data = default_workspace_dict()
    data["publishing"].update(
        {
            "enabled": True,
            "feed_id": "test-feed",
            "name": "Test PaperFlow Feed",
            "publisher_name": "Test Publisher",
            "publisher_url": "https://example.test",
            "data_license": "CC0-1.0",
            "pdf_policy": "link-only",
            "include_pdf_files": False,
        }
    )
    return WorkspaceSettings.model_validate(data)


def _workspace(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "publisher"
    raw = RawPaperRecord(
        paper_uid="arxiv:2607.00001",
        source="arxiv",
        source_id="2607.00001",
        source_version=1,
        metadata={
            "paper_title": "Safe public paper",
            "paper_pdf_url": "https://arxiv.org/pdf/2607.00001",
            "paper_abs_url": "https://arxiv.org/abs/2607.00001",
        },
    )
    identity = AnalysisIdentity(
        provider="mock",
        model="deterministic-v1",
        profile="full_analysis",
        prompt_version="paper-analysis-v2",
        source_content_hash="content",
    )
    ai = AIAnalysisRecord(
        paper_uid=raw.paper_uid,
        analysis_id=identity.analysis_id,
        identity=identity,
        analyzed_at="2026-07-17T12:00:00+08:00",
        status="complete",
        analysis={"ai_summary_short": "Public analysis"},
    )
    raw_path = root / ".paperflow/data/raw/arxiv/2607.00001/v1.json"
    ai_path = (
        root
        / ".paperflow/data/ai/full_analysis/2607.00001/v1"
        / f"{ai.analysis_id}.json"
    )
    raw_path.parent.mkdir(parents=True)
    ai_path.parent.mkdir(parents=True)
    raw_path.write_text(raw.model_dump_json(indent=2), encoding="utf-8")
    ai_path.write_text(ai.model_dump_json(indent=2), encoding="utf-8")
    user = UserPaperRecord(
        paper_uid=raw.paper_uid,
        user={"user_priority": 5, "user_notes": "private"},
    )
    user_path = root / ".paperflow/data/user/2607.00001.yaml"
    user_path.parent.mkdir(parents=True)
    user_path.write_text(user.model_dump_json(indent=2), encoding="utf-8")
    repository_root = Path(__file__).parents[2]
    schema_dir = root / "schemas"
    schema_dir.mkdir()
    for name in [
        "raw-paper.schema.json",
        "ai-analysis.schema.json",
        "feed.schema.json",
        "community-contribution.schema.json",
        "community-profile.schema.json",
        "community-retraction.schema.json",
        "community-manifest.schema.json",
    ]:
        shutil.copy2(repository_root / "schemas" / name, schema_dir / name)
    return root, identity.analysis_id


def test_build_validate_and_sync_feed_without_user_data(tmp_path: Path) -> None:
    publisher, analysis_id = _workspace(tmp_path)
    feed = tmp_path / "feed"

    result = build_feed(publisher, _settings(), feed)

    assert result["paper_count"] == 1
    assert result["analysis_count"] == 1
    assert (feed / "feed.yaml").read_text(encoding="utf-8").startswith(
        "feed_schema_version: 2"
    )
    assert validate_feed(feed)["ok"]
    assert scan_feed(feed) == []
    all_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in feed.rglob("*")
        if path.is_file()
    )
    assert "user_priority" not in all_text
    assert "private" not in all_text
    assert not list(feed.rglob("*.pdf"))
    assert (feed / ".gitattributes").read_text(encoding="utf-8") == (
        "* text=auto eol=lf\n"
    )

    subscriber = tmp_path / "subscriber"
    sync = sync_feed(
        subscriber,
        url=str(feed),
        name="community",
        trust="metadata-and-ai",
    )
    assert sync["created"] == 2
    assert sync["user_records_modified"] == 0
    assert sync["remote_code_executed"] is False
    assert list((subscriber / ".paperflow/data/raw/subscriptions").rglob("*.json"))
    assert list((subscriber / ".paperflow/data/ai/subscriptions").rglob(f"{analysis_id}.json"))
    repeated = sync_feed(
        subscriber,
        url=str(feed),
        name="community",
        trust="metadata-and-ai",
    )
    assert repeated["created"] == 0
    assert repeated["reused"] == 2


def test_standalone_core_sync_preserves_feed_contract(tmp_path: Path) -> None:
    publisher, analysis_id = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(publisher, _settings(), feed)

    core = tmp_path / "core"
    result = sync_core_feed(core, url=str(feed), name="core-feed", trust="metadata-and-ai")
    assert result["created"] == 2
    assert result["remote_code_executed"] is False
    assert list((core / "data/raw/subscriptions").rglob("*.json"))
    assert list((core / "data/ai/subscriptions").rglob(f"{analysis_id}.json"))
    inbox = core / "data/subscriptions/inbox/arxiv_2607.00001.json"
    assert inbox.is_file()
    inbox_record = json.loads(inbox.read_text(encoding="utf-8"))
    assert inbox_record["status"] == "pending-confirmation"
    assert inbox_record["artifact_permission"] == "REMOTE_READ_ONLY"
    repeated = sync_core_feed(core, url=str(feed), name="core-feed", trust="metadata-and-ai")
    assert repeated["created"] == 0
    assert repeated["reused"] == 2
    assert json.loads(inbox.read_text(encoding="utf-8"))["status"] == "pending-confirmation"
    assert not (core / ".paperflow").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="Git not installed")
def test_feed_validates_after_windows_autocrlf_clone(tmp_path: Path) -> None:
    publisher, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(publisher, _settings(), feed)
    subprocess = __import__("subprocess")
    for command in [
        ["git", "init", "-b", "main"],
        ["git", "config", "user.name", "PaperFlow Test"],
        ["git", "config", "user.email", "paperflow@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-m", "fixture"],
    ]:
        subprocess.run(command, cwd=feed, check=True, capture_output=True)
    clone = tmp_path / "clone"
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            "clone",
            str(feed),
            str(clone),
        ],
        check=True,
        capture_output=True,
    )

    assert validate_feed(clone)["checksums"] == "ok"


def test_publisher_does_not_republish_subscription_cache(
    tmp_path: Path,
) -> None:
    publisher, _ = _workspace(tmp_path)
    subscribed_raw = (
        publisher
        / ".paperflow/data/raw/subscriptions/community/arxiv_9999.00001/v1.json"
    )
    subscribed_ai = (
        publisher
        / ".paperflow/data/ai/subscriptions/community/arxiv_9999.00001/analysis.json"
    )
    subscribed_raw.parent.mkdir(parents=True)
    subscribed_ai.parent.mkdir(parents=True)
    subscribed_raw.write_text(
        '{"paper_uid":"arxiv:9999.00001","source":"arxiv",'
        '"source_id":"9999.00001","source_version":1,"metadata":{}}',
        encoding="utf-8",
    )
    subscribed_ai.write_text(
        '{"paper_uid":"arxiv:9999.00001","analysis_id":"remote"}',
        encoding="utf-8",
    )

    result = build_feed(publisher, _settings(), tmp_path / "feed")

    assert result["paper_count"] == 1
    assert result["analysis_count"] == 1
    text = (tmp_path / "feed/manifests/papers.jsonl").read_text(
        encoding="utf-8"
    )
    assert "9999.00001" not in text


def test_rendered_markdown_edits_cannot_change_published_ai_analysis(
    tmp_path: Path,
) -> None:
    publisher, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(publisher, _settings(), feed)
    analysis_manifest = json.loads(
        (feed / "manifests/analyses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    published_ai = feed / analysis_manifest["path"]
    before = published_ai.read_bytes()
    note = publisher / "10 Papers/2026/2607.00001.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\ntype: paper\n---\n\nLocally rewritten analysis and user notes.\n",
        encoding="utf-8",
    )

    build_feed(publisher, _settings(), feed)

    assert published_ai.read_bytes() == before
    assert b"Locally rewritten" not in published_ai.read_bytes()


def test_community_annotation_round_trip_renders_read_only_local_note(
    tmp_path: Path,
) -> None:
    publisher, _ = _workspace(tmp_path)
    snapshot = immutable_snapshot(
        {
            "contribution_id": "ann-roundtrip",
            "paper_uid": "arxiv:2607.00001",
            "kind": "passage-comment",
            "body": "A published annotation comment.",
            "tags": ["method"],
            "anchor": {
                "pdf_version": 1,
                "pdf_sha256": "a" * 64,
                "page": 2,
                "exact_quote": "A short verified quote.",
            },
            "created_at": "2026-07-20T10:00:00+08:00",
        },
        creator="threeyang3",
        license_name="CC-BY-4.0",
    )
    build_outbox(publisher, snapshot, dry_run=False)
    settings = _settings()
    settings = settings.model_copy(
        update={
            "publishing": settings.publishing.model_copy(
                update={"include_community_contributions": True}
            )
        }
    )
    feed = tmp_path / "feed"
    build_feed(publisher, settings, feed)
    subscriber = tmp_path / "subscriber"

    result = sync_feed(
        subscriber,
        url=str(feed),
        name="community",
        trust="metadata-and-ai",
        capabilities=["raw", "ai", "community"],
    )

    assert result["community"]["accepted"] == 1
    assert result["community"]["private_user_records_modified"] == 0
    note = (
        subscriber
        / "70 Community/Unclassified/arxiv_2607.00001.community.md"
    )
    assert note.is_file()
    text = note.read_text(encoding="utf-8")
    assert "# 社区观点 · Safe public paper" in text
    assert "### 段落评论 · @threeyang3" in text
    assert "passage-comment" not in text
    assert "A published annotation comment." in text
    assert "A short verified quote." in text
    assert not (subscriber / ".paperflow/data/user").exists()


def test_standalone_core_community_subscription_isolated_from_user_data(
    tmp_path: Path,
) -> None:
    publisher, _ = _workspace(tmp_path)
    snapshot = immutable_snapshot(
        {
            "contribution_id": "core-ann-roundtrip",
            "paper_uid": "arxiv:2607.00001",
            "kind": "passage-comment",
            "body": "Core community subscription comment.",
            "tags": ["method"],
            "anchor": {
                "pdf_version": 1,
                "pdf_sha256": "a" * 64,
                "page": 2,
                "exact_quote": "A short verified quote.",
            },
            "created_at": "2026-07-20T10:00:00+08:00",
        },
        creator="threeyang3",
        license_name="CC-BY-4.0",
    )
    build_outbox(publisher, snapshot, dry_run=False)
    settings = _settings().model_copy(
        update={
            "publishing": _settings().publishing.model_copy(
                update={"include_community_contributions": True}
            )
        }
    )
    feed = tmp_path / "core-feed"
    build_feed(publisher, settings, feed)
    core = tmp_path / "core"
    result = sync_core_feed(
        core,
        url=str(feed),
        name="core-community",
        trust="metadata-and-ai",
        capabilities=["raw", "ai", "community"],
    )
    assert result["community"]["accepted"] == 1
    assert list((core / "data/community/subscriptions").rglob("r1.json"))
    note = core / "documents/zotero/arxiv_2607.00001.community.md"
    assert note.is_file()
    assert "Core community subscription comment." in note.read_text(encoding="utf-8")
    assert not (core / "data/user").exists() or not list((core / "data/user").rglob("*"))


def test_feed_build_uses_installed_workspace_schemas(tmp_path: Path) -> None:
    publisher, _ = _workspace(tmp_path)
    installed = publisher / ".paperflow/schemas"
    installed.parent.mkdir(parents=True, exist_ok=True)
    (publisher / "schemas").replace(installed)
    feed = tmp_path / "feed"

    result = build_feed(publisher, _settings(), feed)

    schema = json.loads(
        (feed / "schemas/feed.schema.json").read_text(encoding="utf-8")
    )
    assert result["validation"]["ok"]
    assert schema["properties"]["feed_schema_version"]["enum"] == [1, 2]


@pytest.mark.skipif(shutil.which("git") is None, reason="Git not installed")
def test_auto_publish_is_idempotent_and_requires_persisted_authorization(
    tmp_path: Path,
) -> None:
    publisher, _ = _workspace(tmp_path)
    settings = _settings()
    settings = settings.model_copy(
        update={
            "publishing": settings.publishing.model_copy(
                update={
                    "repository_url": "https://github.com/example/paper-feed",
                }
            )
        }
    )
    feed = publisher / ".paperflow/publish/feed"
    init_feed_repository(
        feed,
        remote_url=settings.publishing.repository_url,
    )
    with pytest.raises(ValueError, match="persisted authorization"):
        auto_publish_feed(
            publisher,
            settings,
            push=False,
            confirmed_automation=False,
        )

    first = auto_publish_feed(
        publisher,
        settings,
        push=False,
        confirmed_automation=True,
    )
    second = auto_publish_feed(
        publisher,
        settings,
        push=False,
        confirmed_automation=True,
    )

    assert first["status"] == "committed"
    assert first["privacy_scan"] == "passed"
    assert second["status"] == "unchanged"
    assert second["published"] is False


def test_privacy_scan_blocks_paths_secrets_user_notes_and_pdf(tmp_path: Path) -> None:
    feed = tmp_path / "unsafe"
    feed.mkdir()
    (feed / "unsafe.json").write_text(
        '{"user_priority": 5, "path": "C:/Users/alice/Vault", '
        '"token": "abcdefgh12345678", "body": "USER_NOTES_START"}',
        encoding="utf-8",
    )
    (feed / "paper.pdf").write_bytes(b"%PDF-1.7")

    findings = scan_feed(feed)

    assert any("user field" in item for item in findings)
    assert any("absolute local path" in item for item in findings)
    assert any("possible secret" in item for item in findings)
    assert any("user notes" in item for item in findings)
    assert any("forbidden file" in item for item in findings)


def test_build_requires_license_and_link_only_policy(tmp_path: Path) -> None:
    publisher, _ = _workspace(tmp_path)
    data = default_workspace_dict()
    data["publishing"].update(
        {"feed_id": "x", "name": "x", "data_license": ""}
    )
    with pytest.raises(ValueError, match="data_license"):
        build_feed(
            publisher, WorkspaceSettings.model_validate(data), tmp_path / "feed"
        )


def test_tampered_feed_and_malicious_manifest_path_are_rejected(
    tmp_path: Path,
) -> None:
    publisher, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(publisher, _settings(), feed)
    raw = next((feed / "papers").rglob("v1.json"))
    raw.write_text(raw.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        validate_feed(feed)

    build_feed(publisher, _settings(), feed)
    papers = feed / "manifests/papers.jsonl"
    item = json.loads(papers.read_text(encoding="utf-8").splitlines()[0])
    item["path"] = "../outside.json"
    papers.write_text(json.dumps(item) + "\n", encoding="utf-8")
    checksum = feed / "checksums/sha256.txt"
    lines = [
        line
        for line in checksum.read_text(encoding="utf-8").splitlines()
        if not line.endswith("manifests/papers.jsonl")
    ]
    lines.append(
        __import__("hashlib").sha256(papers.read_bytes()).hexdigest()
        + "  manifests/papers.jsonl"
    )
    checksum.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        validate_feed(feed)


@respx.mock
def test_linked_pdf_download_validates_header_and_hash(tmp_path: Path) -> None:
    content = b"%PDF-1.7\nsynthetic"
    digest = __import__("hashlib").sha256(content).hexdigest()
    respx.get("https://example.test/paper.pdf").mock(
        return_value=httpx.Response(200, content=content)
    )
    item = {
        "paper_uid": "arxiv:2607.00001",
        "source_id": "2607.00001",
        "pdf": {
            "source_url": "https://example.test/paper.pdf",
            "expected_sha256": digest,
            "expected_size": len(content),
        },
    }
    assert _download_linked_pdf(tmp_path, item)
    target = tmp_path / "80 Attachments/Papers/Unclassified/2607.00001/v1.pdf"
    assert target.read_bytes() == content


def test_feed_sync_renders_note_with_selected_analysis(tmp_path: Path) -> None:
    publisher, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(publisher, _settings(), feed)
    subscriber = tmp_path / "subscriber"
    init_workspace(subscriber)
    _, settings = load_workspace_settings(subscriber)
    install_workspace_resources(subscriber, settings)

    result = sync_feed(
        subscriber,
        url=str(feed),
        name="community",
        trust="metadata-and-ai",
        auto_render_notes=True,
    )

    assert result["rendered_notes"] == 1
    note = subscriber / "10 Papers/Unclassified/Safe-public-paper-2607.00001.md"
    assert note.exists()
    text = note.read_text(encoding="utf-8")
    assert "system_selected_analysis_id" in text
    assert "<!-- USER_NOTES_START -->" in text


def test_feed_snapshot_is_zstd_and_checksummed(tmp_path: Path) -> None:
    publisher, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(publisher, _settings(), feed)

    result = create_snapshot(feed, tmp_path / "snapshots")

    archive = Path(result["archive"])
    assert archive.suffixes[-2:] == [".tar", ".zst"]
    assert archive.read_bytes()[:4] == b"\x28\xb5\x2f\xfd"
    assert archive.name in Path(result["checksums"]).read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("git") is None, reason="Git not installed")
def test_feed_snapshot_excludes_git_repository_metadata(tmp_path: Path) -> None:
    publisher, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(publisher, _settings(), feed)
    init_feed_repository(
        feed,
        remote_url="https://github.com/example/paper-feed",
    )
    secret = feed / ".git/private-token.txt"
    secret.write_text("never archive this", encoding="utf-8")

    result = create_snapshot(feed, tmp_path / "snapshots")
    tar_path = tmp_path / "snapshot.tar"
    decompressor = zstandard.ZstdDecompressor()
    with Path(result["archive"]).open("rb") as source, tar_path.open("wb") as target:
        decompressor.copy_stream(source, target)
    with tarfile.open(tar_path) as archive:
        assert not any(".git" in Path(name).parts for name in archive.getnames())


def test_github_repository_url_is_strictly_normalized() -> None:
    assert (
        normalize_github_repository_url(
            "https://github.com/example/paper-feed"
        )
        == "https://github.com/example/paper-feed.git"
    )
    with pytest.raises(ValueError):
        normalize_github_repository_url("git@github.com:example/feed.git")
    with pytest.raises(ValueError):
        normalize_github_repository_url(
            "https://github.com/example/feed.git?token=private"
        )
    with pytest.raises(ValueError):
        normalize_github_repository_url("https://example.com/example/feed")


@pytest.mark.skipif(shutil.which("git") is None, reason="Git not installed")
def test_feed_git_init_disables_hooks_and_git_metadata_is_private(
    tmp_path: Path,
) -> None:
    feed = tmp_path / "feed"
    result = init_feed_repository(
        feed,
        remote_url="https://github.com/example/paper-feed",
        branch="main",
    )

    assert result["created"]
    assert result["origin"].endswith("/example/paper-feed.git")
    assert result["network_contacted"] is False
    status = feed_git_status(feed)
    assert status["repository"]
    assert status["origin"] == result["origin"]
    (feed / ".git/logs").mkdir(parents=True, exist_ok=True)
    (feed / ".git/logs/private.log").write_text(
        "token=not-public", encoding="utf-8"
    )
    assert scan_feed(feed) == []
