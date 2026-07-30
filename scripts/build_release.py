from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from paperflow._version import __version__

VERSION = __version__
DIST = ROOT / "dist"
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git", "node_modules"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def excluded_path(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts) or path.suffix.lower() in EXCLUDED_SUFFIXES


def copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if excluded_path(Path(name))}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def zip_tree(output: Path, source: Path, prefix: str = "") -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and not excluded_path(path.relative_to(source)):
                # ZIP/XPI entries must use POSIX separators even on Windows.
                # Passing a pathlib.Path directly produces backslashes on
                # Windows; Zotero's extension loader then cannot resolve the
                # manifest/bootstrap resources and reports the XPI as
                # incompatible.
                relative = path.relative_to(source).as_posix()
                clean_prefix = prefix.rstrip("/\\")
                arcname = f"{clean_prefix}/{relative}" if clean_prefix else relative
                archive.write(path, arcname)


def copy_selected(stage: Path, names: list[str]) -> None:
    for name in names:
        source = ROOT / name
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=copy_ignore)
        else:
            shutil.copy2(source, target)


def audit_archive(path: Path, *, template_vault: bool = False) -> None:
    with zipfile.ZipFile(path) as archive:
        names = [name.replace("\\", "/") for name in archive.namelist()]
    banned = (
        "/10 Papers/",
        "/30 Reading Notes/",
        "/40 Daily Briefs/",
        "/50 Inbox/",
        "/60 Annotations/",
        "/60 Reviews/",
        "/70 Community/",
        "/80 Attachments/",
        "/.paperflow/data/",
        "/.paperflow/runtime/",
        "/.paperflow/logs/",
        "/.paperflow/cache/",
        "/.paperflow/state/",
        "/.git/",
        "/node_modules/",
    )
    forbidden = [
        name
        for name in names
        if any(fragment in f"/{name}" for fragment in banned)
        or any(f"/{directory}/" in f"/{name}/" for directory in EXCLUDED_DIRS)
        or name.lower().endswith((".pyc", ".pyo"))
        or name.lower().endswith((".pdf", ".sqlite", ".db", ".log", ".wal"))
    ]
    if not template_vault:
        forbidden.extend(name for name in names if "/.obsidian/" in f"/{name}")
    if forbidden:
        raise SystemExit(f"Release archive contains forbidden user data: {forbidden[:10]}")


def main() -> None:
    licence_files = [
        path
        for path in [ROOT / "LICENSE", ROOT / "LICENSE.md", ROOT / "LICENSE-TODO.md"]
        if path.exists()
    ]
    if not licence_files:
        raise SystemExit("Missing software licence or licence decision blocker")
    DIST.mkdir(exist_ok=True)
    for pattern in [
        "paperflow-*.whl",
        "paperflow-*.tar.gz",
        "paperflow-windows-x64-*.zip",
        "PaperFlow-portable-*.zip",
        "PaperFlow-Offline-Installer-*.zip",
        "PaperFlow-Template-Vault-*.zip",
        "schemas-*.zip",
        "templates-*.zip",
        "PaperFlow-Zotero-*.xpi",
    ]:
        for stale in DIST.glob(pattern):
            stale.unlink()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(DIST),
        ],
        cwd=ROOT,
        check=True,
    )
    offline_stage = DIST / f"PaperFlow-Offline-Installer-{VERSION}"
    if offline_stage.exists():
        shutil.rmtree(offline_stage)
    offline_stage.mkdir()
    copy_selected(
        offline_stage,
        [
            "scripts/install.ps1",
            "scripts/uninstall.ps1",
            "scripts/zotero-dev-profile.ps1",
            "schemas",
            "templates",
            "prompts",
            "migrations",
            "integrations",
            "examples/minimal-config",
            "docs",
            "README.md",
            "CHANGELOG.md",
            "LICENSE",
        ],
    )
    wheel = next(DIST.glob(f"paperflow-{VERSION}-*.whl"))
    shutil.copy2(wheel, offline_stage / wheel.name)
    shutil.copy2(ROOT / "scripts/install.ps1", offline_stage / "install.ps1")
    shutil.copy2(ROOT / "scripts/uninstall.ps1", offline_stage / "uninstall.ps1")
    (offline_stage / "paperflow.cmd").write_text(
        "@echo off\r\n"
        "where paperflow >nul 2>nul\r\n"
        "if errorlevel 1 (\r\n"
        "  echo PaperFlow is not installed. Run install.ps1 first.\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        "paperflow %*\r\n",
        encoding="utf-8",
    )
    (offline_stage / "OFFLINE-INSTALL.txt").write_text(
        "PaperFlow Offline Installer Bundle\n\n"
        "This archive contains the wheel, installers, documentation, templates, "
        "and integration resources. It is not a self-contained portable runtime; "
        "installation uses pipx, uv, or pip and then invokes the installed "
        "`paperflow` console script.\n\n"
        "PowerShell examples:\n"
        "  .\\install.ps1 -Method pipx\n"
        "  .\\install.ps1 -Method uv\n"
        "  .\\install.ps1 -Method pip\n",
        encoding="utf-8",
    )
    (offline_stage / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    offline = DIST / f"PaperFlow-Offline-Installer-{VERSION}.zip"
    zip_tree(offline, offline_stage, offline_stage.name)
    audit_archive(offline)
    shutil.rmtree(offline_stage)

    vault_stage = DIST / f"PaperFlow-Template-Vault-{VERSION}"
    if vault_stage.exists():
        shutil.rmtree(vault_stage)
    (vault_stage / ".paperflow").mkdir(parents=True)
    shutil.copy2(
        ROOT / "examples/minimal-config/workspace.yaml",
        vault_stage / ".paperflow/workspace.yaml",
    )
    shutil.copytree(ROOT / "templates", vault_stage / "90 System/Templates")
    shutil.copytree(
        ROOT / "integrations/obsidian-form-flow",
        vault_stage / "90 System/Forms/PaperFlow-Form-Flow-Bundle",
    )
    shutil.copytree(
        ROOT / "integrations/obsidian-pdf-plus",
        vault_stage / "90 System/Integrations/PDF++",
    )
    form_plugin = vault_stage / ".obsidian/plugins/form-flow"
    form_plugin.mkdir(parents=True)
    shutil.copy2(
        ROOT / "integrations/obsidian-form-flow/default-data.json",
        form_plugin / "data.json",
    )
    shutil.copytree(
        ROOT / "integrations/obsidian-paperflow-automation",
        vault_stage / ".obsidian/plugins/paperflow-automation",
        ignore=shutil.ignore_patterns("default-data.json", "integration.json"),
    )
    shutil.copy2(
        ROOT / "integrations/obsidian-paperflow-automation/default-data.json",
        vault_stage / ".obsidian/plugins/paperflow-automation/data.json",
    )
    (vault_stage / ".obsidian/community-plugins.json").write_text(
        json.dumps(["form-flow", "paperflow-automation"], indent=2) + "\n",
        encoding="utf-8",
    )
    template_vault = DIST / f"PaperFlow-Template-Vault-{VERSION}.zip"
    zip_tree(template_vault, vault_stage, vault_stage.name)
    audit_archive(template_vault, template_vault=True)
    shutil.rmtree(vault_stage)

    zip_tree(DIST / f"schemas-{VERSION}.zip", ROOT / "schemas", "schemas")
    zip_tree(DIST / f"templates-{VERSION}.zip", ROOT / "templates", "templates")
    zotero_stage = DIST / f"PaperFlow-Zotero-{VERSION}"
    if zotero_stage.exists():
        shutil.rmtree(zotero_stage)
    shutil.copytree(ROOT / "integrations/zotero-paperflow", zotero_stage)
    zotero_plugin = DIST / f"PaperFlow-Zotero-{VERSION}.xpi"
    zip_tree(zotero_plugin, zotero_stage)
    audit_archive(zotero_plugin)
    shutil.rmtree(zotero_stage)
    # Zotero 9 requires applications.zotero.update_url in the plugin manifest.
    # Publish a standards-compatible update manifest alongside the XPI so the
    # URL is useful after a GitHub Release is created.
    update_manifest = DIST / "zotero-update.json"
    update_manifest.write_text(
        json.dumps(
            {
                "addons": {
                    "paperflow-zotero@threeyang": {
                        "updates": [
                            {
                                "version": VERSION,
                                "update_link": (
                                    "https://github.com/threeyang3/PaperRead/"
                                    f"releases/download/v{VERSION}/PaperFlow-Zotero-{VERSION}.xpi"
                                ),
                            }
                        ]
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    notes = DIST / "migration-notes.md"
    notes.write_text(
        f"# PaperFlow {VERSION} migration notes\n\n"
        "Run `paperflow migrate workspace-v3 --dry-run`, review the zero-network "
        "plan, then run `paperflow migrate workspace-v3 --apply` and "
        "`paperflow migrate verify-workspace-v3`.\n\n"
        "The migration backs up `.obsidian`, private data and every PDF; copies "
        "current PDFs to immutable version paths; creates PDF hash indexes; "
        "installs private Annotation/Review and read-only Community roots; and "
        "rebuilds all Bases without deleting legacy PDFs.\n",
        encoding="utf-8",
    )
    artifacts = sorted(
        path
        for path in DIST.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    )
    (DIST / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
