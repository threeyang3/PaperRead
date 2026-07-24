"""Provider resource paths shared by Vault and standalone Core modes."""

from __future__ import annotations

from pathlib import Path

from paperflow.zotero.store import runtime_root, standalone


def _package_resource(relative: str) -> Path | None:
    try:
        from importlib.resources import files

        candidate = files("paperflow").joinpath("resources", relative)
        path = Path(str(candidate))
        return path if path.is_file() else None
    except (ModuleNotFoundError, TypeError, FileNotFoundError):
        return None


def schema_path(root: Path, name: str = "paper-analysis.schema.json") -> Path:
    candidates = [
        root / ".paperflow/schemas" / name,
        root / "schemas" / name,
        _package_resource(f"schemas/{name}"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"PaperFlow schema not found: {name}")


def prompt_path(root: Path, name: str = "paper-analysis-v3.md") -> Path:
    candidates = [
        root / ".paperflow/prompts" / name,
        root / "prompts" / name,
        _package_resource(f"prompts/{name}"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise FileNotFoundError(f"PaperFlow prompt not found: {name}")


def ai_log_path(root: Path, name: str) -> Path:
    return (root / "logs/ai" if standalone(root) else root / ".paperflow/logs/ai") / name


def provider_runtime_path(root: Path) -> Path:
    path = runtime_root(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = ["ai_log_path", "prompt_path", "provider_runtime_path", "schema_path"]
