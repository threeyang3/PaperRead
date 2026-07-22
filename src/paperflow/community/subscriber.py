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
    community_note_root: str = "70 Community",
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    resolved_note_root = (vault / community_note_root).resolve()
    try:
        resolved_note_root.relative_to(resolved_vault)
    except ValueError as exc:
        raise ValueError("Community note root must stay inside the vault") from exc
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
    all_items: dict[tuple[str, str], CommunityContribution] = {}
    cache_root = vault / ".paperflow/data/community/subscriptions"
    if not dry_run and cache_root.exists():
        cached_files = cache_root.glob("*/papers/*/community/*/*/r*.json")
        candidates = [
            CommunityContribution.model_validate_json(path.read_text(encoding="utf-8"))
            for path in cached_files
        ]
    else:
        candidates = accepted
    for item in candidates:
        key = (item.creator, item.contribution_id)
        previous = all_items.get(key)
        if previous is None or item.revision > previous.revision:
            all_items[key] = item
    rendered_notes = []
    for paper_uid in sorted({item.paper_uid for item in all_items.values()}):
        year = _paper_year(feed_root, paper_uid)
        paper_id = paper_uid.replace(":", "_")
        output = resolved_note_root / year / f"{paper_id}.community.md"
        rendered_notes.append(
            render_community_note(
                vault,
                paper_uid,
                list(all_items.values()),
                output,
                dry_run=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "feed_id": feed_id,
        "accepted": len(accepted),
        "paths": planned,
        "ratings": community_rating_summary(accepted),
        "rendered_notes": rendered_notes,
        "private_user_records_modified": 0,
        "remote_code_executed": False,
    }


def _paper_year(feed_root: Path, paper_uid: str) -> str:
    for path in feed_root.glob("papers/*/raw/v*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("paper_uid")) != paper_uid:
            continue
        metadata = payload.get("metadata") or {}
        year = str(metadata.get("paper_year") or "")
        if not year:
            year = str(metadata.get("paper_submitted_date") or "")[:4]
        return year if re_full_year(year) else "Unclassified"
    return "Unclassified"


def re_full_year(value: str) -> bool:
    return len(value) == 4 and value.isdigit()


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
