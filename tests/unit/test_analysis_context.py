from __future__ import annotations

import pytest
from paperflow.ai.context import select_context


def test_long_chinese_document_with_no_headings_keeps_beginning_and_end() -> None:
    text = "这是开头的研究问题。" + "步骤和证据。" * 12000 + "这是结尾的实验局限。"
    value = select_context(text, limit=5000)
    assert len(value) <= 5000
    assert "这是开头的研究问题。" in value
    assert "这是结尾的实验局限。" in value


def test_context_preserves_short_text_and_rejects_invalid_limits() -> None:
    assert select_context("very short", limit=20) == "very short"
    with pytest.raises(ValueError, match="positive"):
        select_context("abc", limit=0)


def test_long_english_document_includes_middle_and_end() -> None:
    text = "Opening\n" + "a" * 9000 + "\nMETHOD\n" + "b" * 5000 + "\nConclusion\n" + "end" * 1000
    selected = select_context(text, limit=6000)
    assert len(selected) <= 6000
    assert "Opening" in selected
    assert "METHOD" in selected
    assert "endend" in selected
