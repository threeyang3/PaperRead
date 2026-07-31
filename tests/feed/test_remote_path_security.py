from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from paperflow.feed.subscriber import _download_linked_pdf, sync_feed
from paperflow.security.paths import PathSecurityError


def _remote_feed(
    root: Path,
    *,
    feed_id: str = "safe-feed",
    paper_uids: tuple[str, ...] = ("arxiv:2607.00001",),
) -> Path:
    (root / "manifests").mkdir(parents=True)
    entries = []
    for index, paper_uid in enumerate(paper_uids, start=1):
        relative = f"papers/paper-{index}/raw/v1.json"
        target = root / relative
        target.parent.mkdir(parents=True)
        payload = json.dumps({"paper_uid": paper_uid}).encode("utf-8")
        target.write_bytes(payload)
        entries.append(
            {
                "paper_uid": paper_uid,
                "source_id": f"2607.{index:05d}",
                "version": 1,
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "pdf": {"source_url": ""},
            }
        )
    (root / "manifests/papers.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in entries), encoding="utf-8"
    )
    (root / "manifests/analyses.jsonl").write_text("", encoding="utf-8")
    (root / "feed.yaml").write_text(
        "\n".join(
            [
                "feed_schema_version: 2",
                f"feed_id: {json.dumps(feed_id)}",
                "capabilities:",
                "  raw: true",
                "  ai: false",
                "  community: false",
            ]
        ),
        encoding="utf-8",
    )
    return root


def _sync_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, feed_id: str
) -> None:
    feed = _remote_feed(tmp_path / "feed", feed_id=feed_id)
    workspace = tmp_path / "vault"
    outside = tmp_path / "outside-sentinel.txt"
    outside.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr("paperflow.feed.subscriber.validate_feed", lambda _root: {"ok": True})
    with pytest.raises(PathSecurityError):
        sync_feed(workspace, url=str(feed), name="malicious", dry_run=True)
    assert outside.read_text(encoding="utf-8") == "unchanged"
    assert not (workspace / ".paperflow").exists()


def test_feed_subscriber_rejects_feed_id_parent_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sync_dry_run(tmp_path, monkeypatch, feed_id="../../outside")


def test_feed_subscriber_rejects_windows_drive_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sync_dry_run(tmp_path, monkeypatch, feed_id="C:/outside")


def test_feed_subscriber_rejects_unc_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sync_dry_run(tmp_path, monkeypatch, feed_id="//server/share")


def test_feed_subscriber_rejects_absolute_posix_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sync_dry_run(tmp_path, monkeypatch, feed_id="/outside")


def test_feed_subscriber_rejects_source_id_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(PathSecurityError):
        _download_linked_pdf(
            tmp_path,
            {
                "paper_uid": "arxiv:2607.00001",
                "source_id": "../../outside",
                "version": 1,
                "pdf": {"source_url": "https://example.invalid/paper.pdf"},
            },
        )
    assert not (tmp_path / "80 Attachments").exists()


def test_sanitized_identifier_collision_is_rejected_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed = _remote_feed(tmp_path / "feed", paper_uids=("Ａ", "A"))
    workspace = tmp_path / "vault"
    monkeypatch.setattr("paperflow.feed.subscriber.validate_feed", lambda _root: {"ok": True})
    with pytest.raises(PathSecurityError, match="collision"):
        sync_feed(workspace, url=str(feed), name="collision", dry_run=False)
    assert not (workspace / ".paperflow").exists()
