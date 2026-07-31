from __future__ import annotations

from pathlib import Path

from paperflow.zotero.store import ensure_layout, layout, standalone


def test_standalone_data_root_layout(tmp_path: Path) -> None:
    root = tmp_path / "core"
    (root / "data").mkdir(parents=True)
    assert standalone(root)
    paths = ensure_layout(root)
    assert (root / "data/raw").is_dir()
    assert (root / "state").is_dir()
    assert paths["documents_zotero"].endswith("documents/zotero")


def test_vault_layout_remains_compatible(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    (root / ".paperflow").mkdir(parents=True)
    assert not standalone(root)
    assert layout(root)["raw"].as_posix().endswith(".paperflow/data/raw")
