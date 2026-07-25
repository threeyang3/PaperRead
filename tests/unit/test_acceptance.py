from pathlib import Path

from paperflow.acceptance import _audit_project_root


def test_project_root_falls_back_to_editable_source(monkeypatch, tmp_path: Path):
    """Audits launched from a separate Vault still find the source checkout."""
    monkeypatch.chdir(tmp_path)
    root = _audit_project_root()
    assert root is not None
    assert (root / "pyproject.toml").is_file()
    assert (root / "integrations/obsidian-form-flow/integration.json").is_file()
