"""Explicit artifact permissions and publication boundary checks.

PaperFlow has four data layers and two front ends.  A path check alone is not
enough to protect user notes, so every system writer can use this small,
dependency-free guard before an atomic write.  The guard never grants access
to arbitrary paths and never changes user content implicitly.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


class ArtifactPermissionError(PermissionError):
    """Raised when a writer crosses a user/system or publish boundary."""


@dataclass(frozen=True)
class ArtifactPolicy:
    """Repository-relative ownership policy."""

    system_roots: tuple[str, ...] = (
        ".paperflow/data", ".paperflow/state", ".paperflow/runtime",
        ".paperflow/cache", ".paperflow/logs", "data", "state", "runtime",
        "cache", "logs", "documents/zotero", "20 AI Analyses",
    )
    user_roots: tuple[str, ...] = (
        ".paperflow/data/user", "data/user",
        "10 Papers", "20 Topics", "30 Reading Notes", "40 Daily Briefs",
        "50 Inbox", "60 User Notes", "60 Reviews", "70 Community",
        "documents/obsidian",
    )
    publish_forbidden_names: frozenset[str] = frozenset(
        {".env", "auth.json", "paperflow.db", "zotero.sqlite"}
    )
    publish_forbidden_suffixes: frozenset[str] = frozenset(
        {".db", ".sqlite", ".sqlite3", ".log", ".pdf"}
    )

    def relative(self, root: Path, path: Path) -> str:
        root = root.resolve()
        candidate = path.resolve()
        try:
            return candidate.relative_to(root).as_posix().rstrip("/")
        except ValueError as exc:
            raise ArtifactPermissionError(
                f"artifact path escapes configured root: {candidate}"
            ) from exc

    @staticmethod
    def _under(relative: str, roots: Iterable[str]) -> bool:
        value = relative.casefold()
        return any(
            value == root.casefold()
            or value.startswith(root.casefold() + "/")
            for root in roots
        )

    def permission(self, root: Path, path: Path) -> str:
        relative = self.relative(root, path)
        if self._under(relative, self.user_roots):
            return "USER_MANAGED"
        if self._under(relative, self.system_roots):
            return "SYSTEM_MANAGED"
        return "UNCLASSIFIED"

    def assert_permission(self, root: Path, path: Path, permission: str) -> str:
        actual = self.permission(root, path)
        expected = str(permission).upper()
        if expected in {"SYSTEM_MANAGED", "USER_MANAGED"} and actual != expected:
            raise ArtifactPermissionError(
                f"{expected} writer may not write {actual} artifact: "
                f"{self.relative(root, path)}"
            )
        return actual


@dataclass
class PermissionGuard:
    root: Path
    policy: ArtifactPolicy = field(default_factory=ArtifactPolicy)

    def authorize(self, path: Path, permission: str = "SYSTEM_MANAGED") -> Path:
        candidate = path.expanduser().resolve()
        self.policy.assert_permission(self.root, candidate, permission)
        return candidate

    def unchanged(self, path: Path, expected_sha256: str) -> bool:
        candidate = path.expanduser().resolve()
        if not candidate.is_file():
            return False
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        return bool(expected_sha256) and digest.casefold() == expected_sha256.casefold()


class WriteAuthorizer(PermissionGuard):
    """Semantic alias used by write-heavy integrations and plugins."""


@dataclass(frozen=True)
class PublishFinding:
    path: str
    reason: str


class PublishScanner:
    """Reject private/user artifacts before a Feed or package is published."""

    def __init__(self, root: Path, policy: ArtifactPolicy | None = None):
        self.root = root.resolve()
        self.policy = policy or ArtifactPolicy()

    def scan(self, paths: Iterable[Path]) -> list[PublishFinding]:
        findings: list[PublishFinding] = []
        forbidden_names = {value.casefold() for value in self.policy.publish_forbidden_names}
        for raw in paths:
            path = Path(raw)
            relative = self.policy.relative(self.root, path)
            if self.policy.permission(self.root, path) == "USER_MANAGED":
                findings.append(PublishFinding(relative, "user-managed artifact"))
            if path.name.casefold() in forbidden_names:
                findings.append(PublishFinding(relative, "private filename"))
            if path.suffix.casefold() in self.policy.publish_forbidden_suffixes:
                findings.append(PublishFinding(relative, "forbidden publication suffix"))
        return findings

    def assert_clean(self, paths: Iterable[Path]) -> None:
        findings = self.scan(paths)
        if findings:
            joined = "; ".join(f"{item.path}: {item.reason}" for item in findings)
            raise ArtifactPermissionError(
                f"publication boundary rejected artifacts: {joined}"
            )


__all__ = [
    "ArtifactPermissionError", "ArtifactPolicy", "PermissionGuard",
    "PublishFinding", "PublishScanner", "WriteAuthorizer",
]
