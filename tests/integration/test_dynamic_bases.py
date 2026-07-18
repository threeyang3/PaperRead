from __future__ import annotations

from pathlib import Path

from paperflow.obsidian.bases import rebuild_bases


def test_bases_follow_configured_note_and_base_roots(tmp_path: Path) -> None:
    paths = rebuild_bases(
        tmp_path,
        "zh-CN",
        base_root="Dash/Views",
        paper_root="Library/Papers",
        request_roots=("Inbox/New", "Inbox/Done", "Inbox/Failed"),
    )

    assert paths
    assert all(path.is_relative_to(tmp_path / "Dash/Views") for path in paths)
    library = (tmp_path / "Dash/Views/Paper Library.base").read_text(
        encoding="utf-8"
    )
    requests = (tmp_path / "Dash/Views/Paper Requests.base").read_text(
        encoding="utf-8"
    )
    assert 'file.inFolder("Library/Papers")' in library
    assert 'file.inFolder("Inbox/New")' in requests
