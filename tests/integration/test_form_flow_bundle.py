from __future__ import annotations

import json
import shutil
from pathlib import Path

from paperflow.obsidian.form_flow import (
    install_or_upgrade,
    integration_status,
    try_install_official_plugin,
)


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    plugin = vault / ".obsidian/plugins/form-flow"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        json.dumps({"id": "form-flow", "version": "0.0.8"}),
        encoding="utf-8",
    )
    (vault / ".obsidian/community-plugins.json").write_text(
        '["form-flow"]', encoding="utf-8"
    )
    return vault


def test_install_and_status_require_official_form_flow(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    result = install_or_upgrade(vault)

    assert all(
        item["action"] == "installed" for item in result["actions"]
    )
    status = integration_status(vault)
    assert status["healthy"]
    assert status["plugin"]["version"] == "0.0.8"


def test_upgrade_never_overwrites_user_modified_form(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    install_or_upgrade(vault)
    form = vault / "90 System/Forms/添加论文.cform"
    form.write_text('{"user_customized": true}', encoding="utf-8")

    result = install_or_upgrade(vault, mode="upgrade")

    assert form.read_text(encoding="utf-8") == '{"user_customized": true}'
    assert form.with_name(form.name + ".new").exists()
    action = next(item for item in result["actions"] if item["path"].endswith(".cform"))
    assert action["action"] == "merge-review"


def test_official_plugin_install_has_safe_manual_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    result = try_install_official_plugin(tmp_path / "vault")
    assert result["installed"] is False
    assert "form-flow" in result["manual"]
