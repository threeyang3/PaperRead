from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from paperflow.community.models import CommunityContribution, CommunityRetraction
from paperflow.community.privacy import scan_community_contribution
from paperflow.community.publisher import verify_content_sha256
from paperflow.utils import atomic_json, atomic_write, iso_beijing


def community_rating_summary(items: list[CommunityContribution]) -> dict[str, Any]:
    ratings = [item.rating for item in items if item.rating is not None]
    distribution = {str(value): ratings.count(value) for value in range(1, 6)}
    return {
        "count": len(ratings),
        "median": statistics.median(ratings) if ratings else None,
        "minimum": min(ratings) if ratings else None,
        "maximum": max(ratings) if ratings else None,
        "distribution": distribution,
        "creators": len({item.creator for item in items if item.rating is not None}),
        "small_sample_warning": len(ratings) < 5,
    }


def ingest_community(
    vault: Path,
    feed_root: Path,
    feed_id: str,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    files = sorted(feed_root.glob("papers/*/community/*/*/r*.json"))
    accepted: list[CommunityContribution] = []
    planned = []
    for source in files:
        payload = json.loads(source.read_text(encoding="utf-8"))
        value = CommunityContribution.model_validate(payload)
        normalized = value.model_dump(mode="json")
        if not verify_content_sha256(normalized):
            raise ValueError(f"{source}: content_sha256 mismatch")
        findings = scan_community_contribution(normalized)
        if findings:
            raise ValueError(f"{source}: {findings}")
        relative = source.relative_to(feed_root)
        target = vault / ".paperflow/data/community/subscriptions" / feed_id / relative
        planned.append(target.relative_to(vault).as_posix())
        accepted.append(value)
        if not dry_run:
            atomic_json(target, value.model_dump(mode="json"))
    return {
        "dry_run": dry_run,
        "feed_id": feed_id,
        "accepted": len(accepted),
        "paths": planned,
        "ratings": community_rating_summary(accepted),
        "private_user_records_modified": 0,
        "remote_code_executed": False,
    }


def render_community_note(vault: Path, paper_uid: str,
                          items: list[CommunityContribution],
                          output: Path, *, dry_run: bool = True) -> dict[str, Any]:
    visible = [item for item in items if item.paper_uid == paper_uid]
    lines = [
        "---", "type: paperflow-community-note", f"paper_uid: {paper_uid}",
        f"community_count: {len(visible)}", f"updated_at: {iso_beijing()}", "---",
        "", "# 社区观点", "",
        "> 社区内容是只读订阅数据，与个人标注、个人评分和 AI 分析分层保存。", "",
    ]
    for item in visible:
        lines.extend([
            f"## @{item.creator} · {item.kind} · r{item.revision}", "",
            (f"> {item.anchor.exact_quote}" if item.anchor and item.anchor.exact_quote else ""),
            item.body, "",
        ])
    if not dry_run:
        atomic_write(output, "\n".join(lines).rstrip() + "\n")
    return {"dry_run": dry_run, "path": output.relative_to(vault).as_posix(),
            "contributions": len(visible)}
