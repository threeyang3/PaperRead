from __future__ import annotations

import json
from pathlib import Path

from paperflow.zotero.markdown import build_ai_markdown, render_ai_projection


def _record(tmp_path: Path) -> None:
    path = tmp_path / ".paperflow/data/papers/arxiv_2504.16054.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "paper_uid": "arxiv:2504.16054",
                "paper_title_display": "π₀.₅: readable title",
                "paper_authors": ["Author A", "Author B", "Author C"],
                "paper_abs_url": "https://arxiv.org/abs/2504.16054",
                "ai_analysis_status": "complete",
                "ai_summary_short": "A concise summary.",
                "ai_method_family": ["Diffusion Policy"],
                "ai_contributions": ["Contribution one"],
                "user_reading_status": "deep_read",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_ai_markdown_keeps_metadata_in_frontmatter_and_omits_repeated_bio() -> None:
    text = build_ai_markdown({"paper_uid": "arxiv:1", "paper_title": "Title", "paper_authors": ["A", "B", "C"], "ai_summary_short": "Summary"})
    assert "authors:" in text
    assert "## 一句话概述" in text
    assert "A\nB" not in text
    assert "Summary" in text


def test_projection_is_non_overwriting_and_hashable(tmp_path: Path) -> None:
    _record(tmp_path)
    first = render_ai_projection(tmp_path, "arxiv:2504.16054", apply_changes=True)
    assert first["status"] == "written"
    second = render_ai_projection(tmp_path, "arxiv:2504.16054", apply_changes=False)
    assert second["status"] == "up-to-date"
    target = Path(first["path"])
    target.write_text(target.read_text(encoding="utf-8") + "\n我的 Zotero 个人修改\n", encoding="utf-8")
    third = render_ai_projection(tmp_path, "arxiv:2504.16054", apply_changes=True)
    assert third["status"] == "manual-review-required"


def test_projection_supports_both_targets_with_render_state(tmp_path: Path) -> None:
    _record(tmp_path)
    result = render_ai_projection(tmp_path, "arxiv:2504.16054", target="both", apply_changes=True)
    assert result["status"] == "written"
    assert len(result["paths"]) == 2
    assert Path(result["render_state"]).is_file()
    assert Path(result["paths"][0]).is_file()
    assert Path(result["paths"][1]).is_file()
