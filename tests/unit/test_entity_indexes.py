from __future__ import annotations

import json
from pathlib import Path

from paperflow.entity_indexes import (
    INDEX_END,
    INDEX_START,
    rebuild_entity_indexes,
)


def _record(root: Path, uid: str, title: str, *, topics: list[str], methods: list[str]) -> None:
    note = root / "10 Papers" / "2025" / f"{uid.replace(':', '_')}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(f"---\ntype: paper\npaper_uid: {uid}\ntitle: {title}\n---\n", encoding="utf-8")
    data = {
        "paper_uid": uid,
        "paper_arxiv_id": uid.split(":", 1)[-1],
        "paper_title": title,
        "paper_title_display": title,
        "ai_topics": topics,
        "ai_method_family": methods,
        "ai_datasets": [],
        "note_path": note.relative_to(root).as_posix(),
    }
    path = root / ".paperflow/data/papers" / f"{uid.replace(':', '_')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_reverse_indexes_keep_topic_and_method_layers_distinct(tmp_path: Path) -> None:
    _record(
        tmp_path,
        "arxiv:2501.00001",
        "Diffusion Policy in Robotics",
        topics=["Diffusion Policy"],
        methods=["Diffusion-Policy"],
    )
    result = rebuild_entity_indexes(tmp_path, apply=True)
    assert result["entity_count"] == 2
    topic = tmp_path / "20 Topics/Diffusion-Policy.md"
    method = tmp_path / "20 Topics/Methods/Diffusion-Policy.md"
    assert topic.exists() and method.exists()
    topic_text = topic.read_text(encoding="utf-8")
    method_text = method.read_text(encoding="utf-8")
    assert "> 实体类型：主题" in topic_text
    assert "> 实体类型：方法" in method_text
    assert "同名的方法视图" in topic_text
    assert "同名的主题视图" in method_text
    assert INDEX_START in topic_text and INDEX_END in topic_text
    assert "[[10 Papers/2025/arxiv_2501.00001|Diffusion Policy in Robotics]]" in method_text


def test_reverse_indexes_preserve_user_prose(tmp_path: Path) -> None:
    _record(tmp_path, "arxiv:2501.00002", "A Paper", topics=["Robot Learning"], methods=[])
    path = tmp_path / "20 Topics/Robot-Learning.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ntype: topic\ntitle: Robot Learning\n---\n\n# Robot Learning\n\n我的长期观察。\n\n## 相关论文\n",
        encoding="utf-8",
    )
    rebuild_entity_indexes(tmp_path, apply=True)
    text = path.read_text(encoding="utf-8")
    assert "我的长期观察。" in text
    assert "PAPERFLOW_ENTITY_INDEX_START" in text
