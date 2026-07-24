from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperflow.zotero.markdown import render_ai_projection
from paperflow.zotero.standalone_ai import analyze_standalone, load_current_analysis
from paperflow.zotero.store import ensure_layout


def _root(tmp_path: Path) -> Path:
    ensure_layout(tmp_path, force_standalone=True)
    (tmp_path / "data/papers").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.yaml").write_text(
        "schema_version: 1\nstore: paperflow-core\n"
        "analysis:\n  provider: mock\n  profile: full_analysis\n  model: deterministic-v1\n",
        encoding="utf-8",
    )
    (tmp_path / "data/papers/arxiv_2504.16054.json").write_text(
        json.dumps({
            "paper_uid": "arxiv:2504.16054",
            "paper_arxiv_id": "2504.16054",
            "paper_arxiv_version": 1,
            "paper_title": "π0.5: a Vision-Language-Action Model",
            "paper_authors": ["Physical Intelligence"],
            "paper_abstract": "A vision language action model for open-world generalization.",
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def test_standalone_ai_is_append_only_and_renders_projection(tmp_path: Path) -> None:
    root = _root(tmp_path)
    result = analyze_standalone(root, "arxiv:2504.16054")
    assert result["status"] == "written"
    assert result["artifact_permission"] == "AI_VERSIONED"
    assert (root / result["path"]).is_file()
    current = load_current_analysis(root, "arxiv:2504.16054")
    assert current and current["status"] == "complete"

    projection = render_ai_projection(root, "arxiv:2504.16054", target="zotero", apply_changes=True)
    assert projection["status"] == "written"
    note = root / "documents/zotero/arxiv_2504.16054.analysis.md"
    assert "Vision-Language-Action" in note.read_text(encoding="utf-8")
    reused = analyze_standalone(root, "arxiv:2504.16054")
    assert reused["status"] == "reused"
    assert not (root / ".paperflow").exists()


def test_standalone_ai_rejects_unconfigured_external_provider(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "config.yaml").write_text(
        "schema_version: 1\nanalysis:\n  provider: claude\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="standalone provider"):
        analyze_standalone(root, "arxiv:2504.16054")
