from __future__ import annotations

import hashlib
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).parents[2]
DIST = ROOT / "dist"
VERSION = "1.3.1"


def test_fixed_release_artifacts_and_checksums() -> None:
    required = {
        f"paperflow-{VERSION}-py3-none-any.whl",
        f"paperflow-{VERSION}.tar.gz",
        f"paperflow-windows-x64-{VERSION}.zip",
        f"schemas-{VERSION}.zip",
        f"templates-{VERSION}.zip",
        "SHA256SUMS",
        "migration-notes.md",
    }
    assert required <= {path.name for path in DIST.iterdir() if path.is_file()}
    checksums = {}
    for line in (DIST / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        checksums[name] = digest
    for name in required - {"SHA256SUMS"}:
        assert hashlib.sha256((DIST / name).read_bytes()).hexdigest() == checksums[name]


def test_archives_have_product_resources_and_no_current_vault_data() -> None:
    wheel = DIST / f"paperflow-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
        assert "paperflow/cli.py" in wheel_names
        assert "paperflow/resources/schemas/raw-paper.schema.json" in wheel_names
        assert (
            "paperflow/resources/integrations/obsidian-form-flow/integration.json"
            in wheel_names
        )
        assert (
            "paperflow/resources/integrations/obsidian-paperflow-automation/main.js"
            in wheel_names
        )
        assert (
            "paperflow/resources/integrations/obsidian-paperflow-automation/styles.css"
            in wheel_names
        )
    source = DIST / f"paperflow-{VERSION}.tar.gz"
    with tarfile.open(source) as archive:
        source_names = archive.getnames()
    banned = [
        "/.paperflow/data/",
        "/.paperflow/state/",
        "/.paperflow/backups/",
        "/10 Papers/",
        "/40 Daily Briefs/",
        "/50 Inbox/",
        "/80 Attachments/",
        "/.obsidian/",
    ]
    assert not [
        name for name in source_names if any(value in name for value in banned)
    ]


def test_portable_contains_installer_examples_and_no_user_data() -> None:
    portable = DIST / f"paperflow-windows-x64-{VERSION}.zip"
    with zipfile.ZipFile(portable) as archive:
        names = archive.namelist()
    assert any(name.endswith("/install.ps1") for name in names)
    assert any(name.endswith("/uninstall.ps1") for name in names)
    assert any("/schemas/" in name for name in names)
    assert any("/templates/" in name for name in names)
    assert not any(
        fragment in name
        for name in names
        for fragment in [".paperflow/data", "10 Papers", "80 Attachments", ".obsidian"]
    )
