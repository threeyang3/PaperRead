from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.zotero.store import ensure_layout


def _core_root(tmp_path: Path) -> Path:
    root = tmp_path / "PaperFlow Core"
    ensure_layout(root, force_standalone=True)
    (root / "config.yaml").write_text(
        "schema_version: 1\n"
        "zotero:\n"
        "  environment:\n"
        "    local_api_url: http://127.0.0.1:23119/api/\n",
        encoding="utf-8",
    )
    return root


def test_standalone_items_accepts_data_root_and_fixture(tmp_path: Path) -> None:
    root = _core_root(tmp_path)
    fixture = tmp_path / "items.json"
    fixture.write_text(json.dumps([{"paper_uid": "arxiv:2607.00001", "title": "π"}], ensure_ascii=False), encoding="utf-8")
    result = CliRunner().invoke(app, ["zotero", "items", "--data-root", str(root), "--items-json", str(fixture)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["count"] == 1


def test_standalone_compatibility_commands_are_safe(tmp_path: Path) -> None:
    root = _core_root(tmp_path)
    runner = CliRunner()
    for command in ("create-collection", "sync-annotations"):
        result = runner.invoke(app, ["zotero", command, "--data-root", str(root)])
        assert result.exit_code == 0, result.output
        value = json.loads(result.stdout)
        assert value["status"] == "plugin-required"
        assert value["database_access"] is False


def test_standalone_conflicts_reports_only_marked_files(tmp_path: Path) -> None:
    root = _core_root(tmp_path)
    marked = root / "data" / "raw" / "paper-NSConflict.json"
    marked.write_text("{}", encoding="utf-8")
    clean = root / "data" / "raw" / "paper.json"
    clean.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(app, ["zotero", "conflicts", "--data-root", str(root)])
    assert result.exit_code == 0, result.output
    value = json.loads(result.stdout)
    assert value["count"] == 1
    assert "paper-NSConflict.json" in value["conflicts"][0]
