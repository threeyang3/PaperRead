from __future__ import annotations

from pathlib import Path

from paperflow.data.user_store import (
    load_user_record,
    merge_user_data,
    save_user_record,
)


def test_note_projection_wins_and_tags_are_merged(tmp_path: Path) -> None:
    record = {
        "paper_uid": "arxiv:2607.00001",
        "paper_arxiv_id": "2607.00001",
        "user_priority": 2,
        "user_added_tags": ["legacy"],
    }
    save_user_record(
        tmp_path,
        record,
        {"user_priority": 3, "user_added_tags": ["sidecar"]},
    )

    merged = merge_user_data(
        tmp_path,
        record,
        {"user_priority": 5, "user_added_tags": ["note", "sidecar"]},
    )

    assert merged["user_priority"] == 5
    assert merged["user_added_tags"] == ["sidecar", "note"]


def test_save_drops_non_user_fields(tmp_path: Path) -> None:
    record = {
        "paper_uid": "arxiv:2607.00001",
        "paper_arxiv_id": "2607.00001",
    }
    save_user_record(
        tmp_path,
        record,
        {"user_favorite": True, "ai_summary_short": "not user data"},
    )
    loaded = load_user_record(tmp_path, record)
    assert loaded is not None
    assert loaded.user == {"user_favorite": True}
