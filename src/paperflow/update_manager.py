from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from packaging.version import Version

from paperflow.feed.git_ops import normalize_github_repository_url
from paperflow.versioning import APPLICATION_VERSION
from paperflow.workspace_ops import create_workspace_backup


GITHUB_API = "https://api.github.com"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _managed_runtime_version(root: Path) -> str | None:
    version_file = root / ".paperflow" / "src" / "paperflow" / "versioning.py"
    if not version_file.is_file():
        return None
    try:
        tree = ast.parse(version_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "APPLICATION_VERSION"
            for target in targets
        ):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _repository_coordinates(repository_url: str) -> tuple[str, str]:
    normalized = normalize_github_repository_url(repository_url)
    parts = [part for part in urlparse(normalized).path.split("/") if part]
    return parts[0], parts[1].removesuffix(".git")


def _release_payload(repository_url: str) -> dict[str, Any]:
    owner, repository = _repository_coordinates(repository_url)
    response = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repository}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"PaperFlow/{APPLICATION_VERSION}",
        },
        follow_redirects=True,
        timeout=30,
    )
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    value = response.json()
    if value.get("draft") or value.get("prerelease"):
        return {}
    return value


def check_for_update(repository_url: str) -> dict[str, Any]:
    release = _release_payload(repository_url)
    if not release:
        return {
            "installed_version": APPLICATION_VERSION,
            "latest_version": "",
            "update_available": False,
            "release_url": "",
            "reason": "no-published-release",
            "network_checked": True,
        }
    tag = str(release.get("tag_name") or "").strip()
    latest = tag.removeprefix("v")
    parsed = Version(latest)
    assets = {
        str(item.get("name")): str(item.get("browser_download_url"))
        for item in release.get("assets", [])
        if item.get("name") and item.get("browser_download_url")
    }
    return {
        "installed_version": APPLICATION_VERSION,
        "latest_version": str(parsed),
        "update_available": parsed > Version(APPLICATION_VERSION),
        "release_url": str(release.get("html_url") or ""),
        "assets": sorted(assets),
        "network_checked": True,
    }


def _download(url: str, destination: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "github.com",
        "objects.githubusercontent.com",
    }:
        raise ValueError("Update assets must be downloaded from GitHub HTTPS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": f"PaperFlow/{APPLICATION_VERSION}"},
        follow_redirects=True,
        timeout=120,
    ) as response:
        response.raise_for_status()
        if response.url.host not in {
            "github.com",
            "objects.githubusercontent.com",
        }:
            raise ValueError("GitHub update redirected to an untrusted host")
        with temporary.open("wb") as output:
            for block in response.iter_bytes():
                output.write(block)
    temporary.replace(destination)


def stage_update(root: Path, repository_url: str) -> dict[str, Any]:
    release = _release_payload(repository_url)
    if not release:
        return {"status": "no-published-release", "staged": False}
    latest = str(release["tag_name"]).removeprefix("v")
    if Version(latest) <= Version(APPLICATION_VERSION):
        return {
            "status": "current",
            "staged": False,
            "installed_version": APPLICATION_VERSION,
            "latest_version": latest,
        }
    assets = {
        str(item["name"]): str(item["browser_download_url"])
        for item in release.get("assets", [])
    }
    wheel_name = f"paperflow-{latest}-py3-none-any.whl"
    required = [wheel_name, "SHA256SUMS"]
    missing = [name for name in required if name not in assets]
    if missing:
        raise ValueError(f"Release is missing required assets: {missing}")
    destination = root / ".paperflow/updates" / latest
    checksums = destination / "SHA256SUMS"
    wheel = destination / wheel_name
    _download(assets["SHA256SUMS"], checksums)
    _download(assets[wheel_name], wheel)
    expected = {}
    for line in checksums.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if separator and len(digest) == 64:
            expected[name.strip()] = digest.casefold()
    if wheel_name not in expected:
        raise ValueError("SHA256SUMS does not cover the release wheel")
    actual = _sha256(wheel)
    if actual != expected[wheel_name]:
        wheel.unlink(missing_ok=True)
        raise ValueError("Release wheel SHA256 mismatch")
    state = {
        "status": "staged",
        "staged": True,
        "version": latest,
        "wheel": wheel.relative_to(root).as_posix(),
        "sha256": actual,
        "release_url": str(release.get("html_url") or ""),
    }
    (destination / "stage.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return state


def _extract_package(wheel: Path, destination: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        members = [
            item
            for item in archive.infolist()
            if item.filename.startswith("paperflow/")
            and not item.is_dir()
        ]
        if not members:
            raise ValueError("Release wheel does not contain the paperflow package")
        for item in members:
            relative = Path(item.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe wheel member: {item.filename}")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def apply_staged_update(
    root: Path,
    version: str,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Explicit confirmation is required to apply an update")
    managed_version = _managed_runtime_version(root)
    if managed_version is not None and Version(version) <= Version(managed_version):
        return {
            "status": "current",
            "applied": False,
            "current_version": managed_version,
            "requested_version": version,
        }
    update_root = root / ".paperflow/updates" / version
    state_path = update_root / "stage.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Update {version} has not been staged")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    wheel = root / state["wheel"]
    if _sha256(wheel) != state["sha256"]:
        raise ValueError("Staged update no longer matches its verified SHA256")

    workspace_backup = create_workspace_backup(root, label=f"pre-update-{version}")
    runtime_backup = workspace_backup / "runtime-src"
    current = root / ".paperflow/src/paperflow"
    if current.exists():
        shutil.copytree(current, runtime_backup)
    staging = update_root / "apply" / "src"
    if staging.exists():
        shutil.rmtree(staging)
    _extract_package(wheel, staging)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(staging)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from paperflow.versioning import APPLICATION_VERSION;"
                f"assert APPLICATION_VERSION == {version!r};"
                "print(APPLICATION_VERSION)"
            ),
        ],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if probe.returncode:
        raise RuntimeError(f"Staged PaperFlow import failed: {probe.stderr[-1000:]}")

    incoming = staging / "paperflow"
    rollback = update_root / "rollback-paperflow"
    if rollback.exists():
        shutil.rmtree(rollback)
    try:
        if current.exists():
            current.replace(rollback)
        incoming.replace(current)
        environment["PYTHONPATH"] = str(root / ".paperflow/src")
        finalize = subprocess.run(
            [
                sys.executable,
                "-m",
                "paperflow.cli",
                "update",
                "finalize",
                "--vault",
                str(root),
            ],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if finalize.returncode:
            raise RuntimeError(
                "Updated runtime failed Workspace finalization: "
                + (finalize.stderr or finalize.stdout)[-2000:]
            )
    except Exception:
        if current.exists():
            shutil.rmtree(current)
        if rollback.exists():
            rollback.replace(current)
        raise
    return {
        "status": "applied",
        "applied": True,
        "version": version,
        "workspace_backup": workspace_backup.relative_to(root).as_posix(),
        "restart_required": True,
    }
