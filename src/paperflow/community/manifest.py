from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from paperflow.feed.publisher import resolve_feed_file


@dataclass(frozen=True)
class CommunityManifestEntry:
    paper_uid: str
    contribution_id: str
    creator: str
    revision: int
    relative_path: str
    sha256: str
    source: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_community_manifest(feed_root: Path) -> list[CommunityManifestEntry]:
    """Return only explicitly manifested, hash-verified contributions."""

    manifest_root = feed_root / "manifests/community"
    manifests = sorted(manifest_root.glob("*.jsonl")) if manifest_root.is_dir() else []
    if not manifests:
        raise ValueError("Community capability requires a community manifest")
    entries: list[CommunityManifestEntry] = []
    paths: set[str] = set()
    keys: set[tuple[str, str, int]] = set()
    for manifest in manifests:
        for line_number, line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            try:
                relative = str(value["path"])
                key = (
                    str(value["paper_uid"]),
                    str(value["contribution_id"]),
                    int(value["revision"]),
                )
                expected = str(value["sha256"])
                creator = str(value["creator"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid Community manifest entry: {manifest}:{line_number}"
                ) from exc
            if relative in paths:
                raise ValueError(f"duplicate manifest path: {relative}")
            if key in keys:
                raise ValueError(f"duplicate Community business key: {key[0]} {key[1]} r{key[2]}")
            source = resolve_feed_file(feed_root, relative)
            if not source.is_file():
                raise ValueError(f"Community manifest file is missing: {relative}")
            if _sha256(source) != expected:
                raise ValueError(f"Community manifest hash mismatch: {relative}")
            paths.add(relative)
            keys.add(key)
            entries.append(
                CommunityManifestEntry(key[0], key[1], creator, key[2], relative, expected, source)
            )
    return entries


__all__ = ["CommunityManifestEntry", "load_community_manifest"]
