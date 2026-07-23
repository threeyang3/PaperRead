from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
DIST = ROOT / "dist"
VERSION = "1.5.0"
pytestmark = pytest.mark.skipif(
    not DIST.is_dir(),
    reason="release artifacts are audited after scripts/build_release.py",
)


def test_fixed_release_artifacts_and_checksums() -> None:
    required = {
        f"paperflow-{VERSION}-py3-none-any.whl",
        f"paperflow-{VERSION}.tar.gz",
        f"PaperFlow-portable-{VERSION}.zip",
        f"PaperFlow-Template-Vault-{VERSION}.zip",
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
        assert (
            "paperflow/resources/integrations/obsidian-pdf-plus/compatibility.json"
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
        "/60 Annotations/",
        "/60 Reviews/",
        "/70 Community/",
        "/80 Attachments/",
        "/.obsidian/",
    ]
    assert not [
        name for name in source_names if any(value in name for value in banned)
    ]


def test_portable_contains_installer_examples_and_no_user_data() -> None:
    portable = DIST / f"PaperFlow-portable-{VERSION}.zip"
    with zipfile.ZipFile(portable) as archive:
        names = archive.namelist()
    assert any(name.endswith("/install.ps1") for name in names)
    assert any(name.endswith("/uninstall.ps1") for name in names)
    assert any("/schemas/" in name for name in names)
    assert any("/templates/" in name for name in names)
    assert any("/prompts/paper-analysis-v3.md" in name for name in names)
    assert any("/docs/" in name for name in names)
    assert not any(
        fragment in name
        for name in names
        for fragment in [".paperflow/data", "10 Papers", "80 Attachments", ".obsidian"]
    )


def test_template_vault_is_curated_and_contains_no_papers() -> None:
    template = DIST / f"PaperFlow-Template-Vault-{VERSION}.zip"
    with zipfile.ZipFile(template) as archive:
        names = archive.namelist()
    assert any(name.endswith("/.paperflow/workspace.yaml") for name in names)
    assert any("/.obsidian/plugins/paperflow-automation/main.js" in name for name in names)
    assert any("/.obsidian/plugins/form-flow/data.json" in name for name in names)
    assert not any(
        fragment in name
        for name in names
        for fragment in ["10 Papers", "80 Attachments", ".paperflow/data", ".pdf"]
    )


def test_zotero_xpi_is_installable_source_only() -> None:
    plugin = DIST / f"PaperFlow-Zotero-{VERSION}.xpi"
    assert plugin.is_file()
    with zipfile.ZipFile(plugin) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["version"] == VERSION
    assert manifest["applications"]["zotero"]["id"] == "paperflow-zotero@threeyang"
    assert "bootstrap.js" in names and "src/zotero-api.js" in names
    assert not any("zotero.sqlite" in name or name.lower().endswith((".pdf", ".db")) for name in names)
