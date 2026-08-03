from __future__ import annotations

import hashlib
import json
import shutil
import inspect
from pathlib import Path

import pytest

from paperflow.data.records import AIAnalysisRecord, AnalysisIdentity, RawPaperRecord
from paperflow.feed import build_feed, validate_feed
from paperflow.feed.subscriber import _render_local_note
from paperflow.workspace import WorkspaceSettings, default_workspace_dict


def _settings() -> WorkspaceSettings:
    data = default_workspace_dict()
    data["publishing"].update(
        {
            "enabled": True,
            "feed_id": "release-hardening",
            "name": "Release Hardening",
            "publisher_name": "PaperFlow Test",
            "publisher_url": "https://example.invalid",
            "data_license": "CC0-1.0",
            "pdf_policy": "link-only",
            "include_pdf_files": False,
        }
    )
    return WorkspaceSettings.model_validate(data)


def _workspace(tmp_path: Path) -> tuple[Path, RawPaperRecord]:
    root = tmp_path / "workspace"
    raw = RawPaperRecord(
        paper_uid="arxiv:2607.10001",
        source="arxiv",
        source_id="2607.10001",
        source_version=1,
        metadata={
            "paper_title": "Canonical title",
            "paper_authors": ["A. Author"],
            "paper_year": 2026,
            "paper_primary_category": "cs.AI",
            "paper_categories": ["cs.AI"],
            "paper_abstract": "Public abstract",
            "paper_pdf_url": "https://arxiv.org/pdf/2607.10001",
            "paper_abs_url": "https://arxiv.org/abs/2607.10001",
        },
        source_license="arXiv",
        pdf_sha256="a" * 64,
    )
    raw_path = root / ".paperflow/data/raw/arxiv/2607.10001/v1.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(raw.model_dump_json(indent=2), encoding="utf-8")
    identity = AnalysisIdentity(
        provider="mock",
        model="deterministic",
        profile="full_analysis",
        prompt_version="paper-analysis-v2",
        source_content_hash="content",
    )
    ai = AIAnalysisRecord(
        paper_uid=raw.paper_uid,
        analysis_id=identity.analysis_id,
        identity=identity,
        analyzed_at="2026-07-30T12:00:00+08:00",
        status="complete",
        analysis={"summary": "safe"},
    )
    ai_path = root / ".paperflow/data/ai/full_analysis/2607.10001/v1" / f"{ai.analysis_id}.json"
    ai_path.parent.mkdir(parents=True)
    ai_path.write_text(ai.model_dump_json(indent=2), encoding="utf-8")
    return root, raw


def _manifest(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _refresh_checksum(feed: Path, relative: str) -> None:
    checksum = feed / "checksums/sha256.txt"
    target = feed / relative
    replacement = f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {relative}"
    lines = [
        line
        for line in checksum.read_text(encoding="utf-8").splitlines()
        if not line.endswith(f"  {relative}")
    ]
    lines.append(replacement)
    checksum.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")


def test_feed_excludes_raw_capture_from_canonical_manifest(tmp_path: Path) -> None:
    root, raw = _workspace(tmp_path)
    capture = raw.model_copy(update={"metadata": {**raw.metadata, "paper_title": "Capture title"}})
    capture_path = root / ".paperflow/data/raw/arxiv/2607.10001/v1/captures/capture.json"
    capture_path.parent.mkdir(parents=True)
    capture_path.write_text(capture.model_dump_json(indent=2), encoding="utf-8")

    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)

    manifest = _manifest(feed / "manifests/papers.jsonl")
    assert len(manifest) == 1
    published = json.loads((feed / str(manifest[0]["path"])).read_text(encoding="utf-8"))
    assert published["metadata"]["paper_title"] == "Canonical title"
    assert not list(feed.rglob("capture.json"))


def test_feed_has_one_canonical_raw_per_paper_version(tmp_path: Path) -> None:
    root, raw = _workspace(tmp_path)
    captures = root / ".paperflow/data/raw/arxiv/2607.10001/v1/captures"
    captures.mkdir(parents=True)
    for index in range(2):
        (captures / f"{index}.json").write_text(
            raw.model_copy(
                update={"metadata": {**raw.metadata, "paper_title": f"capture-{index}"}}
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )

    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)

    manifest = _manifest(feed / "manifests/papers.jsonl")
    assert [(item["paper_uid"], item["version"]) for item in manifest] == [("arxiv:2607.10001", 1)]


def test_public_raw_uses_allowlisted_projection(tmp_path: Path) -> None:
    root, raw = _workspace(tmp_path)
    raw_path = root / ".paperflow/data/raw/arxiv/2607.10001/v1.json"
    value = raw.model_dump(mode="json")
    value["source_response"] = {
        "reviewer_name": "Private Reviewer",
        "selection_coordinates": [1, 2, 3, 4],
    }
    value["extensions"] = {
        "my_comment": "do not publish",
        "lab_note": "private",
        "private_rating": 5,
        "local_pdf_hint": "D:/Private/paper.pdf",
    }
    value["metadata"]["selection_coordinates"] = [9, 9, 9, 9]
    raw_path.write_text(json.dumps(value), encoding="utf-8")

    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)

    manifest = _manifest(feed / "manifests/papers.jsonl")
    public = json.loads((feed / str(manifest[0]["path"])).read_text(encoding="utf-8"))
    text = json.dumps(public)
    for private in [
        "source_response",
        "extensions",
        "Private Reviewer",
        "selection_coordinates",
        "my_comment",
        "lab_note",
        "private_rating",
        "local_pdf_hint",
    ]:
        assert private not in text


def test_rebuild_removes_disabled_raw_records(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    settings = _settings()
    build_feed(root, settings, feed)
    assert list((feed / "papers").rglob("raw/*.json"))

    settings.publishing.include_raw_metadata = False
    build_feed(root, settings, feed)

    assert not list((feed / "papers").rglob("raw/*.json"))
    assert _manifest(feed / "manifests/papers.jsonl") == []


def test_rebuild_removes_disabled_ai_records(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    settings = _settings()
    build_feed(root, settings, feed)
    assert list((feed / "papers").glob("*/ai/**/*.json"))

    settings.publishing.include_ai_analysis = False
    build_feed(root, settings, feed)

    assert not list((feed / "papers").glob("*/ai/**/*.json"))
    assert _manifest(feed / "manifests/analyses.jsonl") == []


def test_rebuild_removes_deleted_paper_records(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)

    shutil.rmtree(root / ".paperflow/data/raw/arxiv/2607.10001")
    shutil.rmtree(root / ".paperflow/data/ai/full_analysis/2607.10001")
    build_feed(root, _settings(), feed)

    assert not list((feed / "papers").rglob("*.json"))
    assert _manifest(feed / "manifests/papers.jsonl") == []
    assert _manifest(feed / "manifests/analyses.jsonl") == []


def test_failed_staging_build_preserves_current_feed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, raw = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)
    before = _inventory(feed)
    raw_path = root / ".paperflow/data/raw/arxiv/2607.10001/v1.json"
    changed = raw.model_copy(update={"metadata": {**raw.metadata, "paper_title": "changed"}})
    raw_path.write_text(changed.model_dump_json(indent=2), encoding="utf-8")

    import paperflow.feed.publisher as publisher

    monkeypatch.setattr(
        publisher, "validate_feed", lambda _root: (_ for _ in ()).throw(ValueError("boom"))
    )
    with pytest.raises(ValueError, match="boom"):
        build_feed(root, _settings(), feed)

    assert _inventory(feed) == before


def test_feed_managed_sync_preserves_unmanaged_repository_files(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    feed.mkdir()
    (feed / "README.md").write_text("publisher notes\n", encoding="utf-8")
    (feed / ".git").mkdir()
    (feed / ".git/config").write_text("[core]\n", encoding="utf-8")

    build_feed(root, _settings(), feed)
    build_feed(root, _settings(), feed)

    assert (feed / "README.md").read_text(encoding="utf-8") == "publisher notes\n"
    assert (feed / ".git/config").read_text(encoding="utf-8") == "[core]\n"
    assert validate_feed(feed)["checksums"] == "ok"


def test_feed_recovers_persisted_interrupted_managed_sync(tmp_path: Path) -> None:
    import paperflow.feed.publisher as publisher

    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)
    (feed / "README.md").write_text("publisher notes\n", encoding="utf-8")
    before = _inventory(feed)

    transaction = publisher._prepare_managed_feed_sync(feed)
    publisher._write_sync_journal(feed, transaction, phase="applying")
    shutil.rmtree(feed / "manifests")
    (feed / "feed.yaml").write_text("partially-applied: true\n", encoding="utf-8")

    result = build_feed(root, _settings(), feed)

    assert result["content_changed"] is False
    after = _inventory(feed)
    before.pop("checksums/sha256.txt")
    after.pop("checksums/sha256.txt")
    assert after == before
    assert validate_feed(feed)["checksums"] == "ok"
    assert not publisher._sync_journal_path(feed).exists()
    assert not transaction.exists()


def test_feed_rejects_unsafe_persisted_sync_journal(tmp_path: Path) -> None:
    import paperflow.feed.publisher as publisher

    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)
    before = _inventory(feed)
    journal = publisher._sync_journal_path(feed)
    journal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "destination_name": feed.name,
                "transaction_dir": "../outside",
                "managed_paths": list(publisher.MANAGED_FEED_PATHS),
                "phase": "applying",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Unsafe Feed sync journal"):
        publisher._recover_managed_feed_sync(feed)
    assert _inventory(feed) == before


def test_feed_build_is_idempotent(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    first = build_feed(root, _settings(), feed)
    before = _inventory(feed)
    second = build_feed(root, _settings(), feed)

    assert first["content_changed"] is True
    assert second["content_changed"] is False
    assert _inventory(feed) == before
    assert not list(tmp_path.glob(".paperflow-feed-staging-*"))


def test_feed_rejects_duplicate_raw_destination_paths(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)
    manifest_path = feed / "manifests/papers.jsonl"
    line = manifest_path.read_text(encoding="utf-8").strip()
    manifest_path.write_text(f"{line}\n{line}\n", encoding="utf-8")
    _refresh_checksum(feed, "manifests/papers.jsonl")

    with pytest.raises(ValueError, match="duplicate"):
        validate_feed(feed)


def test_feed_manifest_sha_matches_raw_file(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)
    manifest_path = feed / "manifests/papers.jsonl"
    item = _manifest(manifest_path)[0]
    item["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(item) + "\n", encoding="utf-8")
    _refresh_checksum(feed, "manifests/papers.jsonl")

    with pytest.raises(ValueError, match="manifest hash mismatch"):
        validate_feed(feed)


def test_feed_manifest_identity_matches_raw_file(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)
    manifest_path = feed / "manifests/papers.jsonl"
    item = _manifest(manifest_path)[0]
    item["paper_uid"] = "arxiv:wrong"
    manifest_path.write_text(json.dumps(item) + "\n", encoding="utf-8")
    _refresh_checksum(feed, "manifests/papers.jsonl")

    with pytest.raises(ValueError, match="identity mismatch"):
        validate_feed(feed)


def test_feed_rejects_file_missing_from_checksum_inventory(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)
    rogue = feed / "papers/rogue.json"
    rogue.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum inventory mismatch"):
        validate_feed(feed)


def test_feed_content_changed_includes_schema_and_policy_files(tmp_path: Path) -> None:
    root, _ = _workspace(tmp_path)
    feed = tmp_path / "feed"
    build_feed(root, _settings(), feed)
    schema = root / "schemas/feed.schema.json"
    schema.parent.mkdir(parents=True, exist_ok=True)
    source = Path("schemas/feed.schema.json").read_text(encoding="utf-8")
    schema.write_text(
        source.replace('"title":', '"$comment":"changed","title":', 1), encoding="utf-8"
    )

    rebuilt = build_feed(root, _settings(), feed)

    assert rebuilt["content_changed"] is True


def test_remote_source_id_is_not_resolved_with_pdf_glob() -> None:
    implementation = inspect.getsource(_render_local_note)

    assert ".rglob(" not in implementation
    assert "source_version" in implementation
