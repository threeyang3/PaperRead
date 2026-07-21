from __future__ import annotations

import json
from pathlib import Path

from paperflow.obsidian.pdf_plus import configure, install, status


def test_pdf_plus_detect_configure_and_preserve_user_settings(tmp_path: Path) -> None:
    plugin = tmp_path / ".obsidian/plugins/pdf-plus"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(json.dumps({
        "id": "pdf-plus", "version": "0.40.31", "minAppVersion": "1.5.8"
    }), encoding="utf-8")
    (plugin / "data.json").write_text(
        '{"enablePDFEdit": true, "userCustom": 42}', encoding="utf-8"
    )
    assert status(tmp_path)["compatible"]
    preview = configure(tmp_path, dry_run=True)
    assert preview["action"] == "merge-review"
    assert "enablePDFEdit" in preview["conflicts"]
    applied = configure(tmp_path, dry_run=False)
    candidate = plugin / "data.json.new"
    assert candidate.exists()
    assert json.loads(candidate.read_text(encoding="utf-8"))["userCustom"] == 42
    assert json.loads((plugin / "data.json").read_text(encoding="utf-8"))["enablePDFEdit"] is True


def test_pdf_plus_missing_uses_official_install_dry_run(tmp_path: Path) -> None:
    result = install(tmp_path, dry_run=True)
    assert result["action"] == "official-obsidian-install"
    assert result["command"][-1] == "id=pdf-plus"
    assert result["fallback"] == "native-page-link"
