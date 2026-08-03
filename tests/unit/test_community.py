from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from paperflow.community.publisher import (
    build_outbox,
    build_pr_tree,
    immutable_snapshot,
    normalize_private_contribution,
)
from paperflow.community.privacy import scan_community_contribution
from paperflow.community.subscriber import community_rating_summary, ingest_community


def _private(**overrides):
    value = {
        "contribution_id": "contrib-1",
        "paper_uid": "arxiv:2607.00001",
        "kind": "passage-comment",
        "body": "A concise public interpretation.",
        "tags": ["robotics"],
        "anchor": {
            "pdf_version": 1,
            "pdf_sha256": "a" * 64,
            "page": 3,
            "exact_quote": "short source quote",
        },
        "created_at": "2026-07-20T10:00:00+08:00",
    }
    value.update(overrides)
    return value


def _manifest(feed: Path, path: Path, snapshot) -> None:
    relative = path.relative_to(feed).as_posix()
    value = {
        "paper_uid": snapshot.paper_uid,
        "contribution_id": snapshot.contribution_id,
        "creator": snapshot.creator,
        "revision": snapshot.revision,
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    target = feed / "manifests/community/all.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value) + "\n", encoding="utf-8")


def test_private_annotation_requires_explicit_immutable_snapshot(tmp_path: Path) -> None:
    snapshot = immutable_snapshot(_private(), creator="threeyang3", license_name="CC-BY-4.0")
    result = build_outbox(tmp_path, snapshot, dry_run=False)
    assert result["privacy_scan"] == "passed"
    assert result["network_changes"] == 0
    value = json.loads(
        (tmp_path / ".paperflow/data/community/outbox" / result["path"]).read_text(encoding="utf-8")
    )
    assert value["creator"] == "threeyang3"
    assert not any(key.startswith("user_") for key in value)


def test_private_annotation_projection_excludes_local_pdf_coordinates() -> None:
    private = {
        "type": "paperflow-user-annotation",
        "schema_version": 1,
        "annotation_id": "ann-1",
        "paper_uid": "arxiv:2607.00001",
        "kind": "passage-comment",
        "motivation": "commenting",
        "body": "Public comment",
        "tags": ["method"],
        "created_at": "2026-07-20T10:00:00+08:00",
        "updated_at": "2026-07-20T10:00:00+08:00",
        "revisions": [
            {
                "revision": 1,
                "preferred": True,
                "reanchor_method": "created",
                "confidence": 1,
                "status": "exact-hash-match",
                "created_at": "2026-07-20T10:00:00+08:00",
                "anchor": {
                    "pdf_version": 1,
                    "pdf_sha256": "a" * 64,
                    "pdf_path": "80 Attachments/Papers/private.pdf",
                    "page": 2,
                    "fragment_selector": {
                        "type": "FragmentSelector",
                        "page": 2,
                        "rect": [1, 2, 3, 4],
                    },
                    "text_quote_selector": {
                        "type": "TextQuoteSelector",
                        "exact": "quote",
                        "prefix": "before",
                        "suffix": "after",
                    },
                    "selected_text_sha256": "b" * 64,
                    "pdf_selection": "1,2,3,4",
                    "highlight_color": "yellow",
                },
            }
        ],
    }

    public = normalize_private_contribution(private)
    snapshot = immutable_snapshot(public, creator="threeyang3", license_name="CC-BY-4.0")
    payload = snapshot.model_dump(mode="json")

    assert payload["contribution_id"] == "ann-1"
    assert payload["anchor"]["exact_quote"] == "quote"
    assert set(payload["anchor"]) == {
        "pdf_version",
        "pdf_sha256",
        "page",
        "exact_quote",
        "prefix",
        "suffix",
    }
    assert "private.pdf" not in json.dumps(payload)


def test_outbox_snapshot_is_unchanged_after_private_source_edit(tmp_path: Path) -> None:
    private = _private()
    snapshot = immutable_snapshot(private, creator="threeyang3", license_name="CC-BY-4.0")
    result = build_outbox(tmp_path, snapshot, dry_run=False)
    outbox = tmp_path / ".paperflow/data/community/outbox" / result["path"]
    before = outbox.read_bytes()
    private["body"] = "Locally edited later"

    assert outbox.read_bytes() == before


@pytest.mark.parametrize(
    "body,expected",
    [
        ("token=abcdefghijklmnop", "credential-like value"),
        ("C:/Users/alice/Vault", "absolute/local path"),
        ("alice@example.com", "email address"),
        ("<script>alert(1)</script>", "active HTML or unsafe URI scheme"),
        ("![[private.png]]", "image or PDF embedding"),
    ],
)
def test_privacy_blockers(body: str, expected: str) -> None:
    assert expected in scan_community_contribution(_private(body=body))


def test_quote_limit_and_revision_chain() -> None:
    with pytest.raises(ValueError):
        immutable_snapshot(
            _private(
                anchor={
                    "pdf_version": 1,
                    "pdf_sha256": "a" * 64,
                    "page": 1,
                    "exact_quote": "x" * 501,
                }
            ),
            creator="threeyang3",
            license_name="CC-BY-4.0",
        )
    with pytest.raises(ValueError, match="supersedes"):
        immutable_snapshot(
            _private(),
            creator="threeyang3",
            license_name="CC-BY-4.0",
            revision=2,
        )


def test_subscription_is_read_only_and_scores_are_separate(tmp_path: Path) -> None:
    feed = tmp_path / "feed"
    snapshot = immutable_snapshot(
        _private(kind="rating", rating=5, anchor=None),
        creator="reader",
        license_name="CC-BY-4.0",
    )
    path = feed / "papers/arxiv_2607.00001/community/reader/contrib-1/r1.json"
    path.parent.mkdir(parents=True)
    path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    _manifest(feed, path, snapshot)
    result = ingest_community(tmp_path / "vault", feed, "test-feed", dry_run=False)
    assert result["accepted"] == 1
    assert result["private_user_records_modified"] == 0
    assert result["ratings"]["median"] == 5
    assert result["ratings"]["small_sample_warning"] is True
    note = tmp_path / "vault/70 Community/Unclassified/arxiv_2607.00001.community.md"
    assert note.is_file()
    assert "### 评分 · @reader" in note.read_text(encoding="utf-8")


def test_subscription_rejects_tampered_content_hash(tmp_path: Path) -> None:
    feed = tmp_path / "feed"
    snapshot = immutable_snapshot(_private(), creator="reader", license_name="CC-BY-4.0")
    value = snapshot.model_dump(mode="json")
    value["body"] = "Tampered after publication."
    path = feed / "papers/arxiv_2607.00001/community/reader/contrib-1/r1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    _manifest(feed, path, snapshot)

    with pytest.raises(ValueError, match="content_sha256 mismatch"):
        ingest_community(tmp_path / "vault", feed, "test-feed", dry_run=False)

    assert not (tmp_path / "vault/.paperflow/data/community/subscriptions").exists()


def test_subscription_ignores_unmanifested_community_file(tmp_path: Path) -> None:
    feed = tmp_path / "feed"
    trusted = immutable_snapshot(_private(), creator="reader", license_name="CC-BY-4.0")
    trusted_path = feed / "papers/arxiv_2607.00001/community/reader/contrib-1/r1.json"
    trusted_path.parent.mkdir(parents=True)
    trusted_path.write_text(trusted.model_dump_json(indent=2), encoding="utf-8")
    _manifest(feed, trusted_path, trusted)
    rogue = trusted_path.parent.parent / "rogue/contrib-evil/r1.json"
    rogue.parent.mkdir(parents=True)
    rogue.write_text(
        trusted.model_copy(update={"contribution_id": "evil"}).model_dump_json(), encoding="utf-8"
    )

    result = ingest_community(tmp_path / "vault", feed, "test-feed", dry_run=True)

    assert result["accepted"] == 1
    assert all("rogue" not in path for path in result["paths"])


def test_subscription_requires_community_manifest(tmp_path: Path) -> None:
    feed = tmp_path / "feed"
    path = feed / "papers/arxiv_2607.00001/community/reader/contrib-1/r1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="requires a community manifest"):
        ingest_community(tmp_path / "vault", feed, "test-feed", dry_run=True)


def test_pr_build_is_local_dry_run(tmp_path: Path) -> None:
    snapshot = immutable_snapshot(_private(), creator="reader", license_name="CC-BY-4.0")
    build_outbox(tmp_path, snapshot, dry_run=False)
    result = build_pr_tree(tmp_path, tmp_path / "pr", dry_run=True)
    assert result["files"]
    assert result["network_changes"] == 0
    assert not (tmp_path / "pr").exists()
