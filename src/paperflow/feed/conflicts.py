"""Deterministic preserve-both writes for immutable subscription records."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from paperflow.security.paths import resolve_under, safe_storage_component


WriteStatus = Literal["created", "reused", "conflict-created", "conflict-reused"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PreservedWrite:
    path: Path
    status: WriteStatus
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def publish_without_overwrite(temporary: Path, target: Path) -> bool:
    """Atomically publish a same-filesystem temporary file if target is absent."""

    try:
        os.link(temporary, target)
    except FileExistsError:
        return False
    temporary.unlink()
    return True


def conflict_target(original: Path, *, source_id: str, sha256: str) -> Path:
    """Return the auditable idempotent path for one conflicting payload."""

    digest = str(sha256).casefold()
    if not _SHA256.fullmatch(digest):
        raise ValueError("conflict sha256 must be a lowercase hexadecimal digest")
    source = safe_storage_component(source_id, label="conflict source", max_length=40)
    name = f"{original.stem}-{source}-conflict-{digest[:12]}{original.suffix}"
    return resolve_under(original.parent, name, label="subscription conflict path")


def copy_preserving_conflicts(
    source: Path,
    target: Path,
    *,
    source_id: str,
    expected_sha256: str = "",
    dry_run: bool = False,
) -> PreservedWrite:
    """Copy *source* without replacing either canonical or conflict history."""

    source_hash = sha256_file(source)
    if expected_sha256 and source_hash != expected_sha256.casefold():
        raise ValueError(f"Manifest hash mismatch: {source}")

    selected = target
    status: WriteStatus = "created"
    if target.is_file():
        if sha256_file(target) == source_hash:
            return PreservedWrite(target, "reused", source_hash)
        selected = conflict_target(target, source_id=source_id, sha256=source_hash)
        status = "conflict-created"
        if selected.is_file():
            if sha256_file(selected) == source_hash:
                return PreservedWrite(selected, "conflict-reused", source_hash)
            raise RuntimeError("conflict digest path is occupied by different content")

    if dry_run:
        return PreservedWrite(selected, status, source_hash)
    selected.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with (
            source.open("rb") as input_stream,
            tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{selected.name}.",
                suffix=".tmp",
                dir=selected.parent,
                delete=False,
            ) as output_stream,
        ):
            temporary_path = Path(output_stream.name)
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        if selected.exists():
            if sha256_file(selected) == source_hash:
                return PreservedWrite(
                    selected,
                    "conflict-reused" if status == "conflict-created" else "reused",
                    source_hash,
                )
            raise RuntimeError("subscription target changed during atomic copy")
        if publish_without_overwrite(temporary_path, selected):
            temporary_path = None
            return PreservedWrite(selected, status, source_hash)
        if sha256_file(selected) == source_hash:
            return PreservedWrite(
                selected,
                "conflict-reused" if status == "conflict-created" else "reused",
                source_hash,
            )
        raise RuntimeError("subscription target changed during atomic copy")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = [
    "PreservedWrite",
    "WriteStatus",
    "conflict_target",
    "copy_preserving_conflicts",
    "publish_without_overwrite",
    "sha256_file",
]
