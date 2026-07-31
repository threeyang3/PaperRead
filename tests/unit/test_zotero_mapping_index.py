from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperflow.utils import atomic_json
from paperflow.zotero import mapping_index


def _write_mapping(root: Path, name: str, paper_uid: str, item_key: str) -> Path:
    path = root / ".paperflow/data/connectors/zotero/mappings" / f"{name}.json"
    atomic_json(
        path,
        {
            "schema_version": 2,
            "paper_uid": paper_uid,
            "zotero": {"item_key": item_key},
        },
    )
    return path


def test_mapping_index_supports_constant_file_lookup(tmp_path: Path, monkeypatch) -> None:
    _write_mapping(tmp_path, "one", "arxiv:2504.16054", "ITEMONE")
    _write_mapping(tmp_path, "two", "doi:10.1/example", "ITEMTWO")
    value = mapping_index.rebuild_mapping_index(tmp_path)
    assert value["by_item_key"]["ITEMTWO"] == "two.json"

    monkeypatch.setattr(
        mapping_index,
        "rebuild_mapping_index",
        lambda _root: (_ for _ in ()).throw(
            AssertionError("valid index triggered a directory rebuild")
        ),
    )
    assert mapping_index.mapping_for_item(tmp_path, "ITEMONE")["paper_uid"] == ("arxiv:2504.16054")
    assert (
        mapping_index.mapping_for_paper(tmp_path, "doi:10.1/example")["zotero"]["item_key"]
        == "ITEMTWO"
    )


def test_corrupt_mapping_index_is_rebuildable(tmp_path: Path) -> None:
    _write_mapping(tmp_path, "one", "arxiv:2504.16054", "ITEMONE")
    target = mapping_index.index_path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{broken", encoding="utf-8")

    result = mapping_index.mapping_for_item(tmp_path, "ITEMONE")

    assert result and result["paper_uid"] == "arxiv:2504.16054"
    rebuilt = json.loads(target.read_text(encoding="utf-8"))
    assert rebuilt["schema_version"] == 1


def test_duplicate_item_key_is_reported(tmp_path: Path) -> None:
    _write_mapping(tmp_path, "one", "arxiv:one", "DUPLICATE")
    _write_mapping(tmp_path, "two", "arxiv:two", "DUPLICATE")

    with pytest.raises(ValueError, match="duplicate Zotero mapping for item_key"):
        mapping_index.rebuild_mapping_index(tmp_path)
