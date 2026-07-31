from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from paperflow.clock import WorkspaceClock, parse_aware_datetime
from paperflow.config import Config
from paperflow.feed.publisher import build_feed
from paperflow.models import ImportRequest
from paperflow.pipeline.daily_brief import write_daily_brief
from paperflow.workspace import WorkspaceSettings, default_workspace_dict


def _request(created_at: str, processed_at: str | None = None) -> ImportRequest:
    return ImportRequest(
        request_id="request-timezone",
        paper_input="2504.16054",
        created_at=created_at,
        processed_at=processed_at,
    )


def test_rfc3339_timestamps_accept_non_shanghai_offsets_and_z() -> None:
    request = _request(
        "2026-07-30T09:15:00+09:00",
        "2026-07-30T00:20:00Z",
    )

    assert request.created_at.endswith("+09:00")
    assert request.processed_at == "2026-07-30T00:20:00Z"
    assert parse_aware_datetime(request.processed_at).utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    "value",
    ["2026-07-30T09:15:00", "not-a-timestamp"],
)
def test_persisted_timestamps_reject_missing_or_invalid_offset(value: str) -> None:
    with pytest.raises(ValidationError, match="timezone offset|RFC3339"):
        _request(value)


def test_workspace_clock_controls_local_day_boundaries() -> None:
    instant = datetime(2026, 7, 30, 15, 30, tzinfo=timezone.utc)

    tokyo = WorkspaceClock("Asia/Tokyo", now_provider=lambda: instant).now()
    utc = WorkspaceClock("UTC", now_provider=lambda: instant).now()

    assert tokyo.date().isoformat() == "2026-07-31"
    assert tokyo.isoformat().endswith("+09:00")
    assert utc.date().isoformat() == "2026-07-30"
    assert utc.isoformat().endswith("+00:00")


def test_workspace_timezone_must_be_valid_iana_name() -> None:
    data = default_workspace_dict()
    data["timezone"] = "Mars/Olympus"

    with pytest.raises(ValidationError, match="timezone"):
        WorkspaceSettings.model_validate(data)


def test_daily_brief_uses_workspace_timezone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates = tmp_path / "90 System/Templates"
    templates.mkdir(parents=True)
    template = "{{ date }} {{ generated_at }}"
    (templates / "Daily Paper Brief Template.md").write_text(template, encoding="utf-8")
    (templates / "Daily Paper Brief Template.en.md").write_text(template, encoding="utf-8")
    config = Config(
        root=tmp_path,
        data={
            "vault": {
                "timezone": "Asia/Tokyo",
                "language": "en",
                "language_fallback": "en",
                "daily_brief_folder": "40 Daily Briefs",
            }
        },
    )

    class FixedClock:
        def __init__(self, timezone_name: str):
            assert timezone_name == "Asia/Tokyo"

        def now(self) -> datetime:
            return datetime(2026, 7, 31, 0, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

    monkeypatch.setattr("paperflow.pipeline.daily_brief.WorkspaceClock", FixedClock)
    path = write_daily_brief(config, "run-timezone", {}, [], [])

    assert path.name == "2026-07-31.md"
    assert "2026-07-31 00:30" in path.read_text(encoding="utf-8")


def test_feed_generated_at_uses_workspace_timezone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = default_workspace_dict()
    data["timezone"] = "Asia/Tokyo"
    data["publishing"].update(
        {
            "enabled": True,
            "feed_id": "timezone-test",
            "name": "Timezone Test",
            "data_license": "CC0-1.0",
        }
    )
    settings = WorkspaceSettings.model_validate(data)

    class FixedClock:
        def __init__(self, timezone_name: str):
            assert timezone_name == "Asia/Tokyo"

        def iso_now(self) -> str:
            return "2026-07-31T00:30:00+09:00"

    monkeypatch.setattr("paperflow.feed.publisher.WorkspaceClock", FixedClock)
    destination = tmp_path / "feed"
    build_feed(tmp_path, settings, destination)
    current = json.loads((destination / "manifests/current.json").read_text(encoding="utf-8"))

    assert current["generated_at"] == "2026-07-31T00:30:00+09:00"
