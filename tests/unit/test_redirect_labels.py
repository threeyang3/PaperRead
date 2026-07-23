from __future__ import annotations

from pathlib import Path

from paperflow.paths.redirects import apply_redirect_labels, plan_redirect_labels


def test_redirect_labels_decorate_generated_stub_and_preserve_target(tmp_path: Path) -> None:
    target = tmp_path / "10 Papers/2025/Readable-2504.16054.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "---\ntype: paper\npaper_title_display: 'π₀.₅: readable title'\n---\n\n# π₀.₅: readable title\n",
        encoding="utf-8",
    )
    redirect = tmp_path / "10 Papers/2025/2504.16054.md"
    redirect.write_text(
        "---\n"
        "type: paper-redirect\n"
        "paperflow_redirect: true\n"
        "paper_uid: arxiv:2504.16054\n"
        "---\n\n# Moved\n\n[[10 Papers/2025/Readable-2504.16054]]\n",
        encoding="utf-8",
    )

    plan = plan_redirect_labels(tmp_path)
    assert plan["count"] == 1
    result = apply_redirect_labels(tmp_path)
    assert result["status"] == "applied"
    text = redirect.read_text(encoding="utf-8")
    assert "title:" in text and "兼容入口 · π₀.₅: readable title" in text
    assert "# 已迁移：π₀.₅: readable title" in text
    assert "[[10 Papers/2025/Readable-2504.16054|打开论文笔记]]" in text


def test_redirect_labels_do_not_overwrite_custom_content(tmp_path: Path) -> None:
    target = tmp_path / "10 Papers/2025/Paper.md"
    target.parent.mkdir(parents=True)
    target.write_text("---\ntype: paper\ntitle: Paper\n---\n", encoding="utf-8")
    redirect = tmp_path / "10 Papers/2025/2504.1.md"
    redirect.write_text(
        "---\ntype: paper-redirect\npaperflow_redirect: true\npaper_uid: arxiv:2504.1\n---\n\n"
        "# My review\n\n[[10 Papers/2025/Paper]]\n",
        encoding="utf-8",
    )
    plan = plan_redirect_labels(tmp_path)
    assert plan["count"] == 0
    assert "10 Papers/2025/2504.1.md" in plan["manual_review"]
