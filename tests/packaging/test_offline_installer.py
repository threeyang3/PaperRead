from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
DIST = ROOT / "dist"
VERSION = "1.5.0"


@pytest.mark.skipif(
    not DIST.is_dir(),
    reason="release artifacts are audited after scripts/build_release.py",
)
def test_offline_bundle_does_not_claim_true_portability() -> None:
    offline = DIST / f"PaperFlow-Offline-Installer-{VERSION}.zip"
    assert offline.is_file()
    assert not (DIST / f"PaperFlow-portable-{VERSION}.zip").exists()
    with zipfile.ZipFile(offline) as archive:
        names = archive.namelist()
        prefix = f"PaperFlow-Offline-Installer-{VERSION}/"
        readme = archive.read(prefix + "OFFLINE-INSTALL.txt").decode("utf-8")
        assert prefix + "install.ps1" in names
        assert prefix + "uninstall.ps1" in names
        assert prefix + "paperflow.cmd" not in names
    assert "not a self-contained portable runtime" in readme
    assert "no same-name command wrapper" in readme
    assert any(name.endswith(f"paperflow-{VERSION}-py3-none-any.whl") for name in names)


def test_install_script_checks_selected_tool_and_verifies_console_script() -> None:
    script = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
    assert "Get-Command pipx -ErrorAction SilentlyContinue" in script
    assert "Get-Command uv -ErrorAction SilentlyContinue" in script
    assert "Get-Command paperflow -ErrorAction SilentlyContinue" in script
    assert "& $paperflow.Source --version" in script
    assert "& $paperflow.Source --help" in script
    assert "PaperFlow installed" not in script.split("Get-Command paperflow")[0]


def test_uninstall_does_not_delete_vault() -> None:
    script = (ROOT / "scripts/uninstall.ps1").read_text(encoding="utf-8")
    assert "Remove-Item" not in script
    assert "paperflow" in script


@pytest.mark.skipif(sys.platform != "win32", reason="real launcher smoke is Windows-only")
def test_windows_offline_installer_executes_console_script_without_recursion(
    tmp_path: Path,
) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell
    archive_path = DIST / f"PaperFlow-Offline-Installer-{VERSION}.zip"
    if not archive_path.is_file():
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_release.py")],
            cwd=ROOT,
            check=True,
            timeout=300,
        )
    assert archive_path.is_file()
    extraction = tmp_path / "包含 中文 and spaces"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extraction)
    bundle = extraction / f"PaperFlow-Offline-Installer-{VERSION}"
    environment = tmp_path / "isolated runtime"
    subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(environment)],
        check=True,
        timeout=120,
    )
    scripts = environment / "Scripts"
    env = dict(os.environ)
    env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
    subprocess.run(
        [shell, "-NoProfile", "-File", str(bundle / "install.ps1"), "-Method", "pip"],
        cwd=bundle,
        env=env,
        check=True,
        timeout=180,
    )
    for argument in ("--version", "--help"):
        result = subprocess.run(
            [str(scripts / "paperflow.exe"), argument],
            cwd=bundle,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
        if argument == "--version":
            assert VERSION in result.stdout
    vault = tmp_path / "do-not-delete-vault"
    vault.mkdir()
    marker = vault / "user-note.md"
    marker.write_text("private", encoding="utf-8")
    subprocess.run(
        [shell, "-NoProfile", "-File", str(bundle / "uninstall.ps1"), "-Method", "pip"],
        cwd=bundle,
        env=env,
        check=True,
        timeout=120,
    )
    assert marker.read_text(encoding="utf-8") == "private"
