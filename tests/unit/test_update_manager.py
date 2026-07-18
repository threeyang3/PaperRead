from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from paperflow.update_manager import (
    _managed_runtime_version,
    check_for_update,
    stage_update,
)


REPOSITORY = "https://github.com/example/PaperFlow"
API = "https://api.github.com/repos/example/PaperFlow/releases/latest"


def _wheel(version: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "paperflow/versioning.py",
            f'APPLICATION_VERSION = "{version}"\n',
        )
        archive.writestr("paperflow/__init__.py", "")
    return output.getvalue()


def test_managed_runtime_version_reads_deployed_runtime(tmp_path: Path) -> None:
    version_file = (
        tmp_path / ".paperflow" / "src" / "paperflow" / "versioning.py"
    )
    version_file.parent.mkdir(parents=True)
    version_file.write_text(
        'APPLICATION_VERSION = "1.2.0"\n',
        encoding="utf-8",
    )

    assert _managed_runtime_version(tmp_path) == "1.2.0"


@respx.mock
def test_update_check_uses_published_stable_github_release() -> None:
    respx.get(API).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": "v9.0.0",
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/example/PaperFlow/releases/tag/v9.0.0",
                "assets": [],
            },
        )
    )

    result = check_for_update(REPOSITORY)

    assert result["network_checked"] is True
    assert result["latest_version"] == "9.0.0"
    assert result["update_available"] is True


@respx.mock
def test_update_check_handles_repository_without_releases() -> None:
    respx.get(API).mock(return_value=httpx.Response(404))

    result = check_for_update(REPOSITORY)

    assert result["reason"] == "no-published-release"
    assert result["update_available"] is False


@respx.mock
def test_stage_update_requires_and_verifies_sha256(tmp_path: Path) -> None:
    version = "9.0.0"
    wheel_name = f"paperflow-{version}-py3-none-any.whl"
    wheel = _wheel(version)
    digest = hashlib.sha256(wheel).hexdigest()
    checksums = f"{digest}  {wheel_name}\n".encode()
    wheel_url = f"https://github.com/example/PaperFlow/releases/download/v{version}/{wheel_name}"
    sums_url = f"https://github.com/example/PaperFlow/releases/download/v{version}/SHA256SUMS"
    release = {
        "tag_name": f"v{version}",
        "draft": False,
        "prerelease": False,
        "html_url": f"https://github.com/example/PaperFlow/releases/tag/v{version}",
        "assets": [
            {"name": wheel_name, "browser_download_url": wheel_url},
            {"name": "SHA256SUMS", "browser_download_url": sums_url},
        ],
    }
    respx.get(API).mock(return_value=httpx.Response(200, json=release))
    respx.get(wheel_url).mock(return_value=httpx.Response(200, content=wheel))
    respx.get(sums_url).mock(return_value=httpx.Response(200, content=checksums))

    result = stage_update(tmp_path, REPOSITORY)

    assert result["staged"] is True
    staged = tmp_path / result["wheel"]
    assert staged.read_bytes() == wheel
    assert json.loads(
        (staged.parent / "stage.json").read_text(encoding="utf-8")
    )["sha256"] == digest


@respx.mock
def test_stage_update_rejects_hash_mismatch(tmp_path: Path) -> None:
    version = "9.0.0"
    wheel_name = f"paperflow-{version}-py3-none-any.whl"
    wheel_url = f"https://github.com/example/PaperFlow/releases/download/v{version}/{wheel_name}"
    sums_url = f"https://github.com/example/PaperFlow/releases/download/v{version}/SHA256SUMS"
    respx.get(API).mock(
        return_value=httpx.Response(
            200,
            json={
                "tag_name": f"v{version}",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {"name": wheel_name, "browser_download_url": wheel_url},
                    {"name": "SHA256SUMS", "browser_download_url": sums_url},
                ],
            },
        )
    )
    respx.get(wheel_url).mock(return_value=httpx.Response(200, content=b"bad"))
    respx.get(sums_url).mock(
        return_value=httpx.Response(
            200,
            content=(("0" * 64) + f"  {wheel_name}\n").encode(),
        )
    )

    with pytest.raises(ValueError, match="SHA256 mismatch"):
        stage_update(tmp_path, REPOSITORY)
