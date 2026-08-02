from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from paperflow.security.paths import (
    PathSecurityError,
    assert_distinct_storage_components,
    resolve_under,
    safe_storage_component,
)


def test_feed_id_schema_keeps_safe_legacy_identifiers_compatible() -> None:
    schema_path = Path(__file__).parents[2] / "schemas/feed.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    legacy_feed = {
        "feed_schema_version": 1,
        "feed_id": "legacy feed:中文",
        "name": "Legacy",
        "publisher": {"name": "Reader", "url": "https://example.test"},
        "generated_at": "2026-07-31T00:00:00Z",
        "minimum_reader_version": "1.4.0",
        "default_branch": "main",
        "data_license": "CC0-1.0",
        "pdf_policy": "link-only",
        "arxiv_attribution": True,
    }

    validator.validate(legacy_feed)
    current_feed = {
        **legacy_feed,
        "feed_schema_version": 2,
        "community_data_schema_version": 1,
        "capabilities": {"raw": True, "ai": True, "community": False},
        "schemas": {},
        "licenses": {},
        "policy": {},
    }
    assert list(validator.iter_errors(current_feed))


@pytest.mark.parametrize(
    "value",
    ["../feed", "..\\feed", "C:\\feed", "C:/feed", "//server/share", "\\\\server\\share", "/feed"],
)
def test_feed_subscriber_rejects_feed_id_parent_traversal(value: str) -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component(value, label="feed_id")


def test_feed_subscriber_rejects_paper_uid_parent_traversal() -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component("../../paper", label="paper_uid")


def test_feed_subscriber_rejects_source_id_parent_traversal() -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component("../source", label="source_id")


def test_feed_subscriber_rejects_windows_drive_path() -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component("D:\\outside", label="paper_uid")


def test_feed_subscriber_rejects_unc_path() -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component("\\\\server\\share", label="paper_uid")


def test_feed_subscriber_rejects_absolute_posix_path() -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component("/outside", label="paper_uid")


def test_feed_subscriber_rejects_nul_component() -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component("paper\x00secret", label="paper_uid")


def test_feed_publisher_cannot_escape_staging_root(tmp_path: Path) -> None:
    root = tmp_path / "staging"
    with pytest.raises(PathSecurityError):
        resolve_under(root, "..", "outside.json", label="feed staging path")
    assert not (tmp_path / "outside.json").exists()


def test_community_subscriber_cannot_escape_cache_root(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    with pytest.raises(PathSecurityError):
        resolve_under(root, "../outside", label="community cache path")


def test_community_subscriber_cannot_escape_note_root(tmp_path: Path) -> None:
    root = tmp_path / "notes"
    with pytest.raises(PathSecurityError):
        resolve_under(root, "..", "outside.md", label="community note path")


def test_community_creator_cannot_create_nested_path() -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component("alice/review", label="creator")


def test_sanitized_identifier_collision_is_rejected() -> None:
    with pytest.raises(PathSecurityError, match="collision"):
        assert_distinct_storage_components(["Ａ", "A"], label="paper_uid")


def test_symlink_cannot_escape_managed_root(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this host")
    with pytest.raises(PathSecurityError):
        resolve_under(root, "link", "payload.json", label="managed path")
    assert not (outside / "payload.json").exists()


def test_safe_storage_component_preserves_legal_logical_id_stably() -> None:
    first = safe_storage_component("arxiv:2607.00001", label="paper_uid")
    second = safe_storage_component("arxiv:2607.00001", label="paper_uid")
    assert first == second
    assert ":" not in first
    assert "/" not in first and "\\" not in first


@pytest.mark.parametrize("value", ["", " ", ".", "..", "CON", "nul.txt"])
def test_unsafe_or_reserved_storage_component_fails_closed(value: str) -> None:
    with pytest.raises(PathSecurityError):
        safe_storage_component(value, label="identifier")
