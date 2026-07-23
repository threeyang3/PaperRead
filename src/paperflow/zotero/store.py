"""Path helpers for a Vault-backed or standalone PaperFlow data root.

The standalone form is the canonical Core store used by the Zotero-first
workflow.  It intentionally contains no Obsidian workspace state; callers
must opt in to the Vault-backed layout explicitly.
"""

from __future__ import annotations

from pathlib import Path


def standalone(root: Path) -> bool:
    """Return whether ``root`` is a Core data root rather than an Obsidian Vault."""
    return (root / "data").is_dir() and not (root / ".paperflow").exists()


def data_root(root: Path) -> Path:
    return root / "data" if standalone(root) else root / ".paperflow/data"


def state_root(root: Path) -> Path:
    return root / "state" if standalone(root) else root / ".paperflow/state"


def runtime_root(root: Path) -> Path:
    return root / "runtime" if standalone(root) else root / ".paperflow/runtime"


def layout(root: Path, *, force_standalone: bool | None = None) -> dict[str, Path]:
    is_standalone = standalone(root) if force_standalone is None else force_standalone
    return {
        "raw": root / "data/raw" if is_standalone else data_root(root) / "raw",
        "ai": root / "data/ai" if is_standalone else data_root(root) / "ai",
        "annotations": root / "data/annotations" if is_standalone else data_root(root) / "annotations",
        "user": root / "data/user" if is_standalone else data_root(root) / "user",
        "community": root / "data/community" if is_standalone else data_root(root) / "community",
        "subscriptions": root / "data/subscriptions" if is_standalone else data_root(root) / "subscriptions",
        "documents_zotero": root / "documents/zotero" if is_standalone else root / "80 Attachments/Papers",
        "documents_obsidian": root / "documents/obsidian" if is_standalone else root,
        "state": root / "state" if is_standalone else state_root(root),
        "jobs": root / "jobs" if is_standalone else root / ".paperflow/runtime",
        "cache": root / "cache" if is_standalone else root / ".paperflow/cache",
        "backups": root / "backups" if is_standalone else root / ".paperflow/backups",
        "logs": root / "logs" if is_standalone else root / ".paperflow/logs",
        "runtime": root / "runtime" if is_standalone else runtime_root(root),
    }


def ensure_layout(root: Path, *, force_standalone: bool | None = None) -> dict[str, str]:
    paths = layout(root, force_standalone=force_standalone)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return {name: path.as_posix() for name, path in paths.items()}


__all__ = ["data_root", "ensure_layout", "layout", "runtime_root", "standalone", "state_root"]
