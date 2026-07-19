from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


CONFLICT_MARKERS = ("-冲突", "-NSConflict")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def find_sync_conflicts(root: Path) -> list[Path]:
    results: list[Path] = []
    for folder in (
        "00 Dashboard",
        "10 Papers",
        "20 Topics",
        "30 Reading Notes",
        "40 Daily Briefs",
        "50 Inbox",
        "80 Attachments",
        "90 System",
    ):
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and any(marker in path.name for marker in CONFLICT_MARKERS):
                results.append(path)
    return results


def assert_no_sync_conflicts(root: Path) -> None:
    conflicts = find_sync_conflicts(root)
    if conflicts:
        preview = ", ".join(
            path.relative_to(root).as_posix() for path in conflicts[:5]
        )
        raise RuntimeError(
            "PaperFlow paused because sync conflict files exist: " + preview
        )


@dataclass(frozen=True)
class ExpectedFile:
    path: Path
    sha256: str

    @classmethod
    def capture(cls, path: Path) -> "ExpectedFile":
        return cls(path, file_sha256(path))

    def assert_unchanged(self) -> None:
        if file_sha256(self.path) != self.sha256:
            raise RuntimeError(
                f"Concurrent external modification detected: {self.path}"
            )
