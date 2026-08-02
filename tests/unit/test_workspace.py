from __future__ import annotations

from pathlib import Path

import pytest

from paperflow.workspace import (
    default_workspace_dict,
    init_workspace,
    install_workspace_resources,
    load_workspace_settings,
)


def test_init_and_load_arbitrary_vault(tmp_path: Path) -> None:
    vault = tmp_path / "My Vault"
    workspace_file = init_workspace(vault)

    assert workspace_file == vault / ".paperflow/workspace.yaml"
    root, settings = load_workspace_settings(vault)
    assert root == vault.resolve()
    assert settings.timezone == "Asia/Shanghai"
    assert settings.paths.raw_metadata.root == ".paperflow/data/raw"
    assert settings.updates.repository_url == (
        "https://github.com/threeyang3/PaperRead"
    )
    assert settings.updates.require_confirm_apply is True
    assert settings.zotero.enabled is True
    assert settings.zotero.collections.primary.name == "PaperFlow"
    assert settings.zotero.analysis_trigger.mode == "collection_only"
    assert settings.zotero.environment.core_service_port == 23140
    assert settings.integrations.zotero.enabled is True


def test_layering_local_environment_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    init_workspace(vault)
    local = vault / ".paperflow/workspace.local.yaml"
    local.write_text("language_fallback: en\n", encoding="utf-8")
    monkeypatch.setenv("PAPERFLOW__DISCOVERY__LOOKBACK_DAYS", "9")

    _, settings = load_workspace_settings(
        vault, {"discovery": {"lookback_days": 11}}
    )

    assert settings.language_fallback == "en"
    assert settings.discovery.lookback_days == 11


def test_unknown_field_has_actionable_validation_error(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    init_workspace(vault)
    workspace = vault / ".paperflow/workspace.yaml"
    workspace.write_text(
        workspace.read_text(encoding="utf-8") + "\nunknown_key: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"field=unknown_key.*fix=edit"):
        load_workspace_settings(vault)


def test_path_roots_reject_absolute_and_traversal() -> None:
    data = default_workspace_dict()
    data["paths"]["pdf"]["root"] = "../outside"
    from paperflow.workspace import WorkspaceSettings

    with pytest.raises(ValueError):
        WorkspaceSettings.model_validate(data)


def test_resources_install_internal_obsidian_automation(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    init_workspace(vault)
    _, settings = load_workspace_settings(vault)

    result = install_workspace_resources(vault, settings)

    plugin = vault / ".obsidian/plugins/paperflow-automation"
    assert (plugin / "main.js").exists()
    assert (plugin / "manifest.json").exists()
    assert (plugin / "styles.css").exists()
    assert (plugin / "data.json").exists()
    manifest = __import__("json").loads(
        (plugin / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == "1.5.1"
    main_js = (plugin / "main.js").read_text(encoding="utf-8")
    assert 'require("./' not in main_js
    assert not (plugin / "reading-workspace.js").exists()
    assert "controlCenter" in __import__("json").loads(
        (plugin / "data.json").read_text(encoding="utf-8")
    )
    assert result["automation"]["enabled"] is True
    assert "paperflow-automation" in __import__("json").loads(
        (vault / ".obsidian/community-plugins.json").read_text(encoding="utf-8")
    )
    state = __import__("json").loads(
        (
            vault
            / ".paperflow/state/integrations/paperflow-automation.json"
        ).read_text(encoding="utf-8")
    )
    assert state["plugin_version"] == "1.5.1"
    assert state["integration_version"] == 10

    main = plugin / "main.js"
    main.write_text("// user customization\n", encoding="utf-8")
    upgraded = install_workspace_resources(vault, settings)
    assert main.read_text(encoding="utf-8") == "// user customization\n"
    assert main.with_name("main.js.new").exists()
    assert any(
        item["file"] == "main.js" and item["action"] == "merge-review"
        for item in upgraded["automation"]["actions"]
    )
