from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.3.2"
DIST = ROOT / "dist"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def zip_tree(output: Path, source: Path, prefix: str = "") -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, Path(prefix) / path.relative_to(source))


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
        "schemas-*.zip",
        "templates-*.zip",
    ]:
        for stale in DIST.glob(pattern):
            stale.unlink()
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(DIST)],
        cwd=ROOT,
        check=True,
    )
    portable_stage = DIST / f"paperflow-windows-x64-{VERSION}"
    if portable_stage.exists():
        shutil.rmtree(portable_stage)
    portable_stage.mkdir()
    for name in ["scripts/install.ps1", "scripts/uninstall.ps1"]:
        source = ROOT / name
        target = portable_stage / Path(name).name
        shutil.copy2(source, target)
    for source in licence_files:
        shutil.copy2(source, portable_stage / source.name)
    shutil.copytree(ROOT / "schemas", portable_stage / "schemas")
    shutil.copytree(ROOT / "templates", portable_stage / "templates")
    shutil.copytree(ROOT / "examples/minimal-config", portable_stage / "example-config")
    (portable_stage / "paperflow.cmd").write_text(
        "@echo off\r\npython -m paperflow.cli %*\r\n", encoding="utf-8"
    )
    (portable_stage / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    portable = DIST / f"paperflow-windows-x64-{VERSION}.zip"
    zip_tree(portable, portable_stage, portable_stage.name)
    shutil.rmtree(portable_stage)

    zip_tree(DIST / f"schemas-{VERSION}.zip", ROOT / "schemas", "schemas")
    zip_tree(DIST / f"templates-{VERSION}.zip", ROOT / "templates", "templates")
    notes = DIST / "migration-notes.md"
    notes.write_text(
        "# PaperFlow 1.3.2 migration notes\n\n"
        "Run `paperflow migrate plan`, review the zero-network plan, then run "
        "`paperflow migrate apply` and `paperflow migrate verify`.\n\n"
        "For existing local PDFs, run `paperflow migrate visual-assets` to "
        "back up template v2, install template v3, and build Derived figures.\n",
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
