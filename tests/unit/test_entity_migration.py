from __future__ import annotations

from pathlib import Path

from paperflow.entity_migration import (
    apply_entity_normalization,
    entity_key,
    plan_entity_normalization,
)


def test_entity_key_normalizes_hyphens_case_and_spacing() -> None:
    assert entity_key("Diffusion Policy") == entity_key("diffusion-policy")
    assert entity_key("  Diffusion\u2013Policy ") == entity_key("diffusion_policy")


def test_entity_normalization_merges_legacy_topic_and_rewrites_links(
    tmp_path: Path,
) -> None:
    topics = tmp_path / "20 Topics"
    topics.mkdir(parents=True)
    (topics / "Diffusion Policy.md").write_text(
        "---\n"
        "type: topic\n"
        "topic_name: Diffusion Policy\n"
        "aliases: [扩散策略]\n"
        "---\n\n# Diffusion Policy\n",
        encoding="utf-8",
    )
    (topics / "Diffusion-Policy.md").write_text(
        "---\n"
        "type: topic\n"
        "title: Diffusion Policy\n"
        "tags: [entity/topic]\n"
        "---\n\n# Diffusion Policy\n\n## 相关论文\n",
        encoding="utf-8",
    )
    paper = tmp_path / "10 Papers/2025/paper.md"
    paper.parent.mkdir(parents=True)
    paper.write_text(
        "# Paper\n\n[[20 Topics/Diffusion Policy|Diffusion Policy]]\n",
        encoding="utf-8",
    )
    plan = plan_entity_normalization(tmp_path)
    assert plan["duplicate_count"] == 1
    result = apply_entity_normalization(tmp_path)
    assert result["merged"] == ["20 Topics/Diffusion Policy.md"]
    assert not (topics / "Diffusion Policy.md").exists()
    canonical = (topics / "Diffusion-Policy.md").read_text(encoding="utf-8")
    assert "扩散策略" in canonical
    assert "[[20 Topics/Diffusion-Policy|Diffusion Policy]]" in paper.read_text(encoding="utf-8")
    assert (tmp_path / result["backup"] / "files/20 Topics/Diffusion Policy.md").exists()
