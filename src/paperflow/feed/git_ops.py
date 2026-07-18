from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def normalize_github_repository_url(value: str) -> str:
    """Accept only a normal HTTPS GitHub repository URL."""
    raw = value.strip()
    parsed = urlparse(raw)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != "github.com"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.params
    ):
        raise ValueError(
            "Repository URL must be HTTPS in the form "
            "https://github.com/<owner>/<repository>.git"
        )
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or any(part in {".", ".."} for part in parts):
        raise ValueError(
            "Repository URL must identify exactly one GitHub owner/repository"
        )
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository:
        raise ValueError("GitHub owner and repository must not be empty")
    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_."
    )
    if any(character not in allowed for part in (owner, repository) for character in part):
        raise ValueError("GitHub owner/repository contains unsupported characters")
    return f"https://github.com/{owner}/{repository}.git"


def _git(
    feed_root: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    if not shutil.which("git"):
        raise RuntimeError("Git is not installed or is not on PATH")
    result = subprocess.run(
        ["git", "-C", str(feed_root), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1000:]
        raise RuntimeError(f"Git command failed: {detail}")
    return result


def init_feed_repository(
    feed_root: Path,
    *,
    remote_url: str,
    branch: str = "main",
) -> dict[str, Any]:
    remote = normalize_github_repository_url(remote_url)
    if not branch or any(character.isspace() for character in branch):
        raise ValueError("Git branch must be a non-empty name without whitespace")
    feed_root.mkdir(parents=True, exist_ok=True)
    created = not (feed_root / ".git").exists()
    if created:
        result = _git(feed_root, "init", "-b", branch, check=False)
        if result.returncode:
            _git(feed_root, "init")
            _git(feed_root, "branch", "-M", branch)
    hooks = (feed_root / ".git/paperflow-disabled-hooks").resolve()
    hooks.mkdir(parents=True, exist_ok=True)
    _git(feed_root, "config", "--local", "core.hooksPath", str(hooks))
    current = _git(
        feed_root, "remote", "get-url", "origin", check=False
    )
    if current.returncode:
        _git(feed_root, "remote", "add", "origin", remote)
    elif current.stdout.strip() != remote:
        raise ValueError(
            "Origin already points to a different repository; "
            "PaperFlow will not replace it automatically"
        )
    return {
        "repository": str(feed_root),
        "created": created,
        "branch": branch,
        "origin": remote,
        "hooks_disabled": True,
        "network_contacted": False,
    }


def feed_git_status(feed_root: Path) -> dict[str, Any]:
    if not shutil.which("git"):
        return {
            "available": False,
            "repository": False,
            "detail": "Git is not installed or is not on PATH",
        }
    if not (feed_root / ".git").exists():
        return {
            "available": True,
            "repository": False,
            "path": str(feed_root),
            "changes": [],
        }
    status = _git(feed_root, "status", "--porcelain=v1", "--branch")
    lines = status.stdout.splitlines()
    branch = lines[0][3:] if lines and lines[0].startswith("## ") else ""
    remote = _git(
        feed_root, "remote", "get-url", "origin", check=False
    )
    changes = lines[1:] if lines and lines[0].startswith("## ") else lines
    return {
        "available": True,
        "repository": True,
        "path": str(feed_root),
        "branch": branch,
        "origin": remote.stdout.strip() if remote.returncode == 0 else "",
        "dirty": bool(changes),
        "changes": changes,
    }
