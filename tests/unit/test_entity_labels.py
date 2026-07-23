from __future__ import annotations

from pathlib import Path

from paperflow.entity_labels import apply_entity_display_labels, plan_entity_display_labels


def _note(path: Path, title: str, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntype: {kind}\ntitle: {title}\ntags:\n  - entity/{kind}\n---\n\n# {title}\n\n## 相关论文\n",
        encoding="utf-8",
    )


def test_entity_display_labels_reuse_human_friendly_variant(tmp_path: Path) -> None:
    _note(tmp_path / "20 Topics/Diffusion-Policy.md", "Diffusion Policy", "topic")
    _note(tmp_path / "20 Topics/Methods/diffusion-policy.md", "diffusion policy", "method")

    plan = plan_entity_display_labels(tmp_path)
    assert any(item["path"].endswith("Methods/diffusion-policy.md") for item in plan["changes"])
    result = apply_entity_display_labels(tmp_path)
    assert result["status"] == "applied"
    method = (tmp_path / "20 Topics/Methods/diffusion-policy.md").read_text(encoding="utf-8")
    assert "title: Diffusion Policy" in method
    assert "# Diffusion Policy" in method
    assert "diffusion policy" in method


def test_entity_display_labels_preserves_body(tmp_path: Path) -> None:
    path = tmp_path / "20 Topics/Methods/foo.md"
    _note(path, "foo", "method")
    path.write_text(path.read_text(encoding="utf-8") + "\n我的方法笔记\n", encoding="utf-8")
    _note(tmp_path / "20 Topics/Foo.md", "Foo", "topic")
    apply_entity_display_labels(tmp_path)
    assert "我的方法笔记" in path.read_text(encoding="utf-8")

