from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperflow.community.publisher import build_outbox, build_pr_tree, immutable_snapshot
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


def test_private_annotation_requires_explicit_immutable_snapshot(tmp_path: Path) -> None:
    snapshot = immutable_snapshot(
        _private(), creator="threeyang3", license_name="CC-BY-4.0"
    )
    result = build_outbox(tmp_path, snapshot, dry_run=False)
    assert result["privacy_scan"] == "passed"
    assert result["network_changes"] == 0
    value = json.loads((tmp_path / ".paperflow/data/community/outbox" / result["path"]).read_text(encoding="utf-8"))
    assert value["creator"] == "threeyang3"
    assert not any(key.startswith("user_") for key in value)


@pytest.mark.parametrize("body,expected", [
    ("token=abcdefghijklmnop", "credential-like value"),
    ("C:/Users/alice/Vault", "absolute/local path"),
    ("alice@example.com", "email address"),
    ("<script>alert(1)</script>", "active HTML or unsafe URI scheme"),
    ("![[private.png]]", "image or PDF embedding"),
])
def test_privacy_blockers(body: str, expected: str) -> None:
    assert expected in scan_community_contribution(_private(body=body))


def test_quote_limit_and_revision_chain() -> None:
    with pytest.raises(ValueError):
        immutable_snapshot(
            _private(anchor={
                "pdf_version": 1, "pdf_sha256": "a" * 64, "page": 1,
                "exact_quote": "x" * 501,
            }),
            creator="threeyang3", license_name="CC-BY-4.0",
        )
    with pytest.raises(ValueError, match="supersedes"):
        immutable_snapshot(
            _private(), creator="threeyang3", license_name="CC-BY-4.0",
            revision=2,
        )


def test_subscription_is_read_only_and_scores_are_separate(tmp_path: Path) -> None:
    feed = tmp_path / "feed"
    snapshot = immutable_snapshot(
        _private(kind="rating", rating=5, anchor=None),
        creator="reader", license_name="CC-BY-4.0",
    )
    path = feed / "papers/arxiv_2607.00001/community/reader/contrib-1/r1.json"
    path.parent.mkdir(parents=True)
    path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    result = ingest_community(tmp_path / "vault", feed, "test-feed", dry_run=False)
    assert result["accepted"] == 1
    assert result["private_user_records_modified"] == 0
    assert result["ratings"]["median"] == 5
    assert result["ratings"]["small_sample_warning"] is True


def test_subscription_rejects_tampered_content_hash(tmp_path: Path) -> None:
    feed = tmp_path / "feed"
    snapshot = immutable_snapshot(
        _private(), creator="reader", license_name="CC-BY-4.0"
    )
    value = snapshot.model_dump(mode="json")
    value["body"] = "Tampered after publication."
    path = feed / "papers/arxiv_2607.00001/community/reader/contrib-1/r1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="content_sha256 mismatch"):
        ingest_community(tmp_path / "vault", feed, "test-feed", dry_run=False)

    assert not (tmp_path / "vault/.paperflow/data/community/subscriptions").exists()


def test_pr_build_is_local_dry_run(tmp_path: Path) -> None:
    snapshot = immutable_snapshot(
        _private(), creator="reader", license_name="CC-BY-4.0"
    )
    build_outbox(tmp_path, snapshot, dry_run=False)
    result = build_pr_tree(tmp_path, tmp_path / "pr", dry_run=True)
    assert result["files"]
    assert result["network_changes"] == 0
    assert not (tmp_path / "pr").exists()
