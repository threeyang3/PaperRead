from __future__ import annotations

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
        launcher = archive.read(prefix + "paperflow.cmd").decode("utf-8")
        readme = archive.read(prefix + "OFFLINE-INSTALL.txt").decode("utf-8")
        assert prefix + "install.ps1" in names
        assert prefix + "uninstall.ps1" in names
    assert "python -m paperflow" not in launcher
    assert "paperflow %*" in launcher
    assert "not a self-contained portable runtime" in readme
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
