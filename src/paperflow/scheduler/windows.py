from __future__ import annotations
import subprocess
from pathlib import Path


def run_script(root: Path, name: str) -> subprocess.CompletedProcess[str]:
    script = root / ".paperflow/scheduler" / name
    return subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)], cwd=root, capture_output=True, text=True)


def install(root: Path): return run_script(root, "install-tasks.ps1")
def uninstall(root: Path): return run_script(root, "uninstall-tasks.ps1")
def status(root: Path): return run_script(root, "show-task-status.ps1")
def run_now(root: Path):
    return subprocess.run(["schtasks.exe", "/Run", "/TN", "ArxivLearn-PaperFlow-Daily"], capture_output=True, text=True)

