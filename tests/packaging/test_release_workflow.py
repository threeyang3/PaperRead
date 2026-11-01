from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_ci_and_release_reuse_the_same_quality_gates() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    expected = "uses: ./.github/workflows/quality-gates.yml"
    assert expected in ci
    assert expected in release


def test_release_workflow_is_draft_first_and_environment_protected() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "environment: production-release" in release
    assert "draft: true" in release
    assert "gh release edit \"$GITHUB_REF_NAME\" --draft=false" in release
    assert "git merge-base --is-ancestor" in release
    assert "SHA256SUMS covers every release artifact" in release


def test_quality_workflow_covers_declared_release_matrix_and_contracts() -> None:
    workflow = (ROOT / ".github/workflows/quality-gates.yml").read_text(encoding="utf-8")
    for value in (
        'python: ["3.11", "3.12", "3.13"]',
        "os: [ubuntu-latest, windows-latest, macos-latest]",
        "mode: [locked, latest-compatible]",
        "ruff check .",
        "ruff format --check .",
        "mypy src/paperflow",
        "pip-audit -r requirements/release-py313.txt",
        "python scripts/check_coverage.py coverage.json",
        "node tests/integration/test_automation_plugin_lifecycle.js",
        "python scripts/build_release.py",
        "python -m pytest tests/packaging -q",
    ):
        assert value in workflow


def test_external_actions_are_pinned_to_full_commit_shas() -> None:
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        for action, reference in re.findall(r"uses:\s+([^\s@]+)@([^\s#]+)", text):
            if action.startswith("./"):
                continue
            assert re.fullmatch(r"[0-9a-f]{40}", reference), (path.name, action, reference)


def test_release_locks_cover_supported_python_versions_with_hashes() -> None:
    for version in ("311", "312", "313"):
        lock = ROOT / f"requirements/release-py{version}.txt"
        text = lock.read_text(encoding="utf-8")
        assert "--hash=sha256:" in text
        assert "paperflow @ file:" not in text


def test_release_always_requests_full_gates_without_cancellation() -> None:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    release = yaml.load((ROOT / ".github/workflows/release.yml").read_text())
    assert release["jobs"]["quality-gates"]["with"] == {"full": True, "docs-only": False}
    assert "concurrency" not in release
    assert release["jobs"]["release"]["needs"] == "quality-gates"
    quality = yaml.load((ROOT / ".github/workflows/quality-gates.yml").read_text())
    assert quality["on"]["workflow_call"]["inputs"]["full"]["default"] is True
    assert quality["on"]["workflow_call"]["inputs"]["docs-only"]["default"] is False
    assert quality["jobs"]["release-build"]["needs"] == "quality"
    commands = [step.get("run", "") for step in quality["jobs"]["quality"]["steps"]]
    assert "python -m pytest --cov=paperflow --cov-report=term-missing --cov-report=json" in commands
    smoke = "\n".join(step.get("run", "") for step in quality["jobs"]["release-build"]["steps"])
    assert "& $paperflow init" in smoke
    assert "& $paperflow workspace info" in smoke
    assert "& $paperflow doctor" in smoke


def test_diagnostic_workflows_no_longer_duplicate_push_and_pr_runs() -> None:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    for name in ("build.yml", "feed-validation.yml", "migration-tests.yml"):
        workflow = yaml.load((ROOT / ".github/workflows" / name).read_text())
        assert set(workflow["on"]) == {"workflow_dispatch"}
    ci = yaml.load((ROOT / ".github/workflows/ci.yml").read_text())
    assert ci["on"]["push"]["branches"] == ["main"]
    assert ci["concurrency"]["cancel-in-progress"] is True
