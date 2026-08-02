from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from paperflow._version import __version__ as VERSION


ROOT = Path(__file__).parents[2]
DIST = ROOT / "dist"


@pytest.fixture(scope="module", autouse=True)
def current_release_artifacts() -> None:
    expected = (
        DIST / f"paperflow-{VERSION}-py3-none-any.whl",
        DIST / f"PaperFlow-Offline-Installer-{VERSION}.zip",
        DIST / f"PaperFlow-Template-Vault-{VERSION}.zip",
        DIST / f"PaperFlow-Obsidian-{VERSION}.zip",
        DIST / f"PaperFlow-Zotero-{VERSION}.xpi",
        DIST / "SHA256SUMS",
    )
    if not all(path.is_file() for path in expected):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_release.py")],
            cwd=ROOT,
            check=True,
            timeout=300,
        )


def test_fixed_release_artifacts_and_checksums() -> None:
    required = {
        f"paperflow-{VERSION}-py3-none-any.whl",
        f"paperflow-{VERSION}.tar.gz",
        f"PaperFlow-Offline-Installer-{VERSION}.zip",
        f"PaperFlow-Template-Vault-{VERSION}.zip",
        f"PaperFlow-Obsidian-{VERSION}.zip",
        f"PaperFlow-Zotero-{VERSION}.xpi",
        f"schemas-{VERSION}.zip",
        f"templates-{VERSION}.zip",
        "main.js",
        "manifest.json",
        "styles.css",
        "zotero-update.json",
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
        assert "paperflow/resources/integrations/obsidian-form-flow/integration.json" in wheel_names
        assert (
            "paperflow/resources/integrations/obsidian-paperflow-automation/main.js" in wheel_names
        )
        assert (
            "paperflow/resources/integrations/obsidian-paperflow-automation/styles.css"
            in wheel_names
        )
        assert (
            "paperflow/resources/integrations/obsidian-pdf-plus/compatibility.json" in wheel_names
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
    assert not [name for name in source_names if any(value in name for value in banned)]


def test_offline_installer_contains_resources_and_no_user_data() -> None:
    offline = DIST / f"PaperFlow-Offline-Installer-{VERSION}.zip"
    with zipfile.ZipFile(offline) as archive:
        names = archive.namelist()
    assert any(name.endswith("/install.ps1") for name in names)
    assert any(name.endswith("/uninstall.ps1") for name in names)
    assert any(name.endswith("/zotero-dev-profile.ps1") for name in names)
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


def test_obsidian_release_contains_installable_plugin_assets() -> None:
    source = ROOT / "integrations/obsidian-paperflow-automation"
    plugin = DIST / f"PaperFlow-Obsidian-{VERSION}.zip"
    assert plugin.is_file()
    with zipfile.ZipFile(plugin) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("paperflow-automation/manifest.json"))
    required = {
        "paperflow-automation/main.js",
        "paperflow-automation/manifest.json",
        "paperflow-automation/styles.css",
        "paperflow-automation/scheduler-core.js",
        "paperflow-automation/reading-workspace.js",
        "paperflow-automation/default-data.json",
        "paperflow-automation/README.md",
    }
    assert required <= names
    assert manifest["id"] == "paperflow-automation"
    assert manifest["version"] == VERSION
    assert not any(
        name.endswith(("data.json", ".pdf", ".db", ".sqlite", ".log"))
        for name in names
        if not name.endswith("default-data.json")
    )
    for name in ["main.js", "manifest.json", "styles.css"]:
        assert (DIST / name).read_bytes() == (source / name).read_bytes()


def test_zotero_xpi_is_valid_source_package() -> None:
    plugin = DIST / f"PaperFlow-Zotero-{VERSION}.xpi"
    assert plugin.is_file()
    with zipfile.ZipFile(plugin) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
    # XPI/ZIP member names are always POSIX paths.  A Windows pathlib.Path
    # passed to ZipFile.write() would produce backslashes and Zotero 9 would
    # fail to resolve the root manifest, reporting the plugin as incompatible.
    assert all("\\" not in name for name in names)
    assert manifest["version"] == VERSION
    assert manifest["applications"]["zotero"]["id"] == "paperflow-zotero@threeyang"
    assert manifest["applications"]["zotero"]["update_url"].startswith(
        "https://github.com/threeyang3/PaperRead/"
    )
    assert manifest["applications"]["zotero"]["strict_min_version"] == "9.0"
    assert manifest["applications"]["zotero"]["strict_max_version"] == "10.99.99"
    assert "bootstrap.js" in names and "prefs.js" in names and "src/zotero-api.js" in names
    assert "install.rdf" not in names
    assert not any(
        "zotero.sqlite" in name or name.lower().endswith((".pdf", ".db")) for name in names
    )
    # The XPI is intentionally unsigned for this local build. Zotero 9's
    # official build accepts ordinary third-party extension installs when the
    # manifest is complete; the Extension Proxy remains the safer development
    # path because it avoids copying code into a user profile.
    assert not any(name.startswith("META-INF/") for name in names)
    update_manifest = DIST / "zotero-update.json"
    assert update_manifest.is_file()
    update = json.loads(update_manifest.read_text(encoding="utf-8"))
    record = update["addons"]["paperflow-zotero@threeyang"]["updates"][0]
    assert record["version"] == VERSION
    assert record["update_link"].endswith(f"PaperFlow-Zotero-{VERSION}.xpi")


def test_zotero_dev_profile_uses_confined_extension_proxy() -> None:
    script = (ROOT / "scripts/zotero-dev-profile.ps1").read_text(encoding="utf-8")
    assert "integrations\\zotero-paperflow" in script
    assert "paperflow-zotero@threeyang" in script
    assert "ProfilePath 必须位于 PaperRead\\var 下" in script
    assert "Remove-Item -LiteralPath $profile -Recurse -Force" in script
    assert "extensions\\.lastApp(BuildId|Version)" in script


def test_zotero_e2e_profile_confines_data_root_to_var() -> None:
    script = (ROOT / "scripts/zotero-e2e.ps1").read_text(encoding="utf-8")
    assert 'Join-Path $profile "zotero-data"' in script
    assert "extensions.zotero.useDataDir" in script
