from pathlib import Path

from importlib import metadata

import paperflow.acceptance as acceptance
from paperflow.acceptance import _audit_project_root


def test_project_root_falls_back_to_editable_source(monkeypatch, tmp_path: Path):
    """Audits launched from a separate Vault still find the source checkout."""
    monkeypatch.chdir(tmp_path)
    root = _audit_project_root()
    assert root is not None
    assert (root / "pyproject.toml").is_file()
    assert (root / "integrations/obsidian-form-flow/integration.json").is_file()


def test_audit_project_root_honors_explicit_environment(monkeypatch, tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PAPERFLOW_PROJECT_ROOT", str(root))

    assert _audit_project_root() == root


def test_audit_project_root_rejects_malformed_distribution_metadata(
    monkeypatch, tmp_path: Path
):
    class BrokenDistribution:
        def read_text(self, _name: str) -> str:
            return "{"

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PAPERFLOW_PROJECT_ROOT", raising=False)
    monkeypatch.setattr(acceptance, "_project_root", lambda: None)
    monkeypatch.setattr(metadata, "distribution", lambda _name: BrokenDistribution())

    assert _audit_project_root() is None


def test_installed_distribution_files_handles_missing_and_present_metadata(monkeypatch):
    def missing(_name: str):
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(metadata, "distribution", missing)
    assert acceptance._installed_distribution_files() == set()

    class PresentDistribution:
        files = [Path("paperflow/cli.py"), Path("paperflow/resources/schema.json")]

    monkeypatch.setattr(metadata, "distribution", lambda _name: PresentDistribution())
    assert acceptance._installed_distribution_files() == {
        "paperflow/cli.py",
        "paperflow/resources/schema.json",
    }
