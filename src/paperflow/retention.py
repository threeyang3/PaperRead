from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from paperflow.utils import now_beijing


def cleanup_ai_logs(root: Path, keep_days: int) -> int:
    cutoff = (now_beijing() - timedelta(days=keep_days)).timestamp()
    removed = 0
    for path in (root / ".paperflow/logs/ai").glob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed
