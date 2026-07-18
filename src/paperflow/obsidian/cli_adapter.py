from __future__ import annotations
import shutil
import subprocess


def obsidian_available() -> bool:
    return shutil.which("obsidian") is not None


def run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("obsidian")
    if not executable:
        raise RuntimeError("Obsidian CLI is unavailable")
    return subprocess.run([executable, *args], capture_output=True, text=True, timeout=timeout)

