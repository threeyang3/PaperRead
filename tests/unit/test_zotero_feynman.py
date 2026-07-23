from __future__ import annotations

from pathlib import Path

import pytest

from paperflow.zotero.feynman import ensure_questions, load_answers, save_answer


def test_feynman_questions_and_answers_are_separate_user_data(tmp_path: Path) -> None:
    (tmp_path / ".paperflow").mkdir()
    result = ensure_questions(tmp_path, "arxiv:2504.16054", ["Why does this work?"], apply_changes=True)
    assert result["status"] == "written"
    state = load_answers(tmp_path, "arxiv:2504.16054")
    question = state["questions"][0]
    saved = save_answer(tmp_path, "arxiv:2504.16054", question["id"], "Because the ablation supports the claim.")
    assert saved["status"] == "written"
    assert load_answers(tmp_path, "arxiv:2504.16054")["answers"][question["id"]]["answer"].startswith("Because")


def test_feynman_rejects_unknown_question(tmp_path: Path) -> None:
    (tmp_path / ".paperflow").mkdir()
    ensure_questions(tmp_path, "arxiv:1", ["Question"], apply_changes=True)
    with pytest.raises(ValueError):
        save_answer(tmp_path, "arxiv:1", "fq-unknown", "Answer")
