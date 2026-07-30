from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo


def parse_aware_datetime(value: str | datetime, *, field: str = "timestamp") -> datetime:
    """Parse an RFC 3339/ISO 8601 timestamp and require an explicit offset."""

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field} must be a valid RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed


@dataclass(frozen=True)
class WorkspaceClock:
    timezone_name: str
    now_provider: Callable[[], datetime] = datetime.now
    timezone: ZoneInfo = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timezone", ZoneInfo(self.timezone_name))

    def now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None or current.utcoffset() is None:
            current = current.astimezone()
        return current.astimezone(self.timezone)

    def iso_now(self, *, timespec: str = "seconds") -> str:
        return self.now().isoformat(timespec=timespec)

    def convert(self, value: str | datetime) -> datetime:
        return parse_aware_datetime(value).astimezone(self.timezone)
