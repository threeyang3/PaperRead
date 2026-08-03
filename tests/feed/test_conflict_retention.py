from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable

import pytest

from paperflow.feed.conflicts import copy_preserving_conflicts
from paperflow.feed.subscriber import sync_feed
from paperflow.zotero.standalone_sync import sync_core_feed


Sync = Callable[[Path, Path], dict]


def _feed(root: Path, payload: dict) -> Path:
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    (root / "manifests/analyses.jsonl").write_text("", encoding="utf-8")
    (root / "feed.yaml").write_text(
        "\n".join(
            [
                "feed_schema_version: 2",
                "feed_id: deterministic-feed",
                "minimum_reader_version: 1.5.1",
                "capabilities:",
                "  raw: true",
                "  ai: false",
                "  community: false",
            ]
        ),
        encoding="utf-8",
    )
    _replace_payload(root, payload)
    return root


def _replace_payload(root: Path, payload: dict) -> str:
    relative = "papers/paper/raw/v1.json"
    source = root / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    source.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    manifest = {
        "paper_uid": "arxiv:2607.00001",
        "source_id": "2607.00001",
        "version": 1,
        "path": relative,
        "sha256": digest,
        "pdf": {"source_url": ""},
    }
    (root / "manifests/papers.jsonl").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    return digest


def _vault_sync(target: Path, feed: Path) -> dict:
    return sync_feed(
        target,
        url=str(feed),
        name="conflict-test",
        trust="metadata-only",
    )


def _standalone_sync(target: Path, feed: Path) -> dict:
    return sync_core_feed(
        target,
        url=str(feed),
        name="conflict-test",
        trust="metadata-only",
    )


@pytest.fixture(autouse=True)
def bypass_unrelated_feed_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    result = {"ok": True}
    monkeypatch.setattr("paperflow.feed.subscriber.validate_feed", lambda _root: result)
    monkeypatch.setattr("paperflow.zotero.standalone_sync.validate_feed", lambda _root: result)


@pytest.mark.parametrize("synchronize", [_vault_sync, _standalone_sync])
def test_second_conflict_does_not_overwrite_first_conflict(
    tmp_path: Path, synchronize: Sync
) -> None:
    feed = _feed(tmp_path / "feed", {"value": "original"})
    target = tmp_path / "subscriber"
    synchronize(target, feed)

    second = {"value": "second"}
    second_hash = _replace_payload(feed, second)
    second_result = synchronize(target, feed)
    third = {"value": "third"}
    third_hash = _replace_payload(feed, third)
    third_result = synchronize(target, feed)

    conflict_paths = {path.name: path for path in target.rglob("*.json") if "conflict" in path.name}
    assert len(conflict_paths) == 2
    contents = {path.read_text(encoding="utf-8") for path in conflict_paths.values()}
    assert json.dumps(second, sort_keys=True) in contents
    assert json.dumps(third, sort_keys=True) in contents
    assert any(second_hash[:12] in name for name in conflict_paths)
    assert any(third_hash[:12] in name for name in conflict_paths)
    assert second_result["conflicts"][0]["status"] == "conflict-created"
    assert third_result["conflicts"][0]["status"] == "conflict-created"


@pytest.mark.parametrize("synchronize", [_vault_sync, _standalone_sync])
def test_identical_conflict_is_reused(tmp_path: Path, synchronize: Sync) -> None:
    feed = _feed(tmp_path / "feed", {"value": "original"})
    target = tmp_path / "subscriber"
    synchronize(target, feed)
    conflict = {"value": "conflict"}
    conflict_hash = _replace_payload(feed, conflict)
    created = synchronize(target, feed)
    reused = synchronize(target, feed)

    assert created["conflicts"][0]["status"] == "conflict-created"
    assert reused["conflicts"][0]["status"] == "conflict-reused"
    assert created["conflicts"][0]["target"] == reused["conflicts"][0]["target"]
    path = Path(reused["conflicts"][0]["target"])
    if not path.is_absolute():
        path = target / path
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == conflict_hash


@pytest.mark.parametrize("synchronize", [_vault_sync, _standalone_sync])
def test_conflict_filename_is_deterministic(tmp_path: Path, synchronize: Sync) -> None:
    feed = _feed(tmp_path / "feed", {"value": "original"})
    target = tmp_path / "subscriber"
    synchronize(target, feed)
    digest = _replace_payload(feed, {"value": "deterministic"})

    result = synchronize(target, feed)

    assert Path(result["conflicts"][0]["target"]).name.endswith(f"conflict-{digest[:12]}.json")


def test_conflict_publish_never_uses_overwriting_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text('{"new": true}', encoding="utf-8")

    def overwrite_probe(_source, destination) -> None:
        Path(destination).write_text('{"racer": true}', encoding="utf-8")
        raise AssertionError("overwriting replace must not publish immutable records")

    monkeypatch.setattr(os, "replace", overwrite_probe)

    result = copy_preserving_conflicts(source, target, source_id="feed")

    assert result.status == "created"
    assert target.read_text(encoding="utf-8") == '{"new": true}'
