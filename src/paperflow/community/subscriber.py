from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from paperflow.community.models import CommunityContribution
from paperflow.community.privacy import scan_community_contribution
from paperflow.community.publisher import verify_content_sha256
from paperflow.obsidian.frontmatter import dump_frontmatter, read_note
from paperflow.text_quality import display_title
from paperflow.utils import atomic_json, atomic_write, iso_utc
from paperflow.security.paths import (
    assert_distinct_storage_components,
    resolve_under,
    safe_storage_component,
)


COMMUNITY_KIND_LABELS = {
    "highlight": "高亮",
    "passage-comment": "段落评论",
    "question": "疑问",
    "critique": "批评",
    "figure-comment": "图评论",
    "section-comment": "章节评论",
    "paper-review": "论文评审",
    "rating": "评分",
    "reply": "回复",
}


def _community_kind_label(kind: str) -> str:
    return COMMUNITY_KIND_LABELS.get(kind, kind)


def _display_quote(value: str) -> str:
    return value.replace("\n", " ").strip().lstrip(":： ").strip()


def _paper_context(vault: Path, feed_root: Path, paper_uid: str) -> tuple[str, str]:
    paper_id = paper_uid.replace(":", "_")
    source_id = paper_uid.split(":", 1)[-1]
    candidates = [
        *(vault / "10 Papers").rglob(f"{paper_id}.md"),
        *(vault / "10 Papers").rglob(f"{source_id}.md"),
    ]
    for note in sorted(set(candidates)):
        try:
            frontmatter, _ = read_note(note)
        except Exception:
            continue
        title = frontmatter.get("paper_title_display") or frontmatter.get("title")
        pdf_path = frontmatter.get("paper_pdf_path") or ""
        if title:
            return display_title(str(title)), str(pdf_path)
    for raw in sorted(feed_root.glob(f"papers/{paper_id}/raw/v*.json")):
        try:
            payload = json.loads(raw.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metadata = payload.get("metadata") or {}
        title = metadata.get("paper_title")
        if title:
            return display_title(str(title)), ""
    return paper_uid, ""


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
    note_parts = Path(community_note_root.replace("\\", "/")).parts
    resolved_note_root = resolve_under(
        vault, *note_parts, label="Community note root"
    )
    try:
        resolved_note_root.relative_to(resolved_vault)
    except ValueError as exc:
        raise ValueError("Community note root must stay inside the vault") from exc
    files = sorted(feed_root.glob("papers/*/community/*/*/r*.json"))
    accepted: list[CommunityContribution] = []
    planned = []
    feed_component = safe_storage_component(feed_id, label="feed_id")
    loaded: list[tuple[Path, CommunityContribution]] = []
    for source in files:
        payload = json.loads(source.read_text(encoding="utf-8"))
        value = CommunityContribution.model_validate(payload)
        normalized = value.model_dump(mode="json")
        if not verify_content_sha256(normalized):
            raise ValueError(f"{source}: content_sha256 mismatch")
        findings = scan_community_contribution(normalized)
        if findings:
            raise ValueError(f"{source}: {findings}")
        loaded.append((source, value))
    paper_components = assert_distinct_storage_components(
        [value.paper_uid for _, value in loaded], label="paper_uid"
    )
    for source, value in loaded:
        relative = source.relative_to(feed_root)
        target = resolve_under(
            vault / ".paperflow/data/community/subscriptions",
            feed_component,
            *relative.parts,
            label="Community subscription cache path",
        )
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
        year = _paper_year(feed_root, paper_uid, vault)
        paper_id = paper_components.get(
            paper_uid, safe_storage_component(paper_uid, label="paper_uid")
        )
        year_component = safe_storage_component(year, label="paper year")
        output = resolve_under(
            resolved_note_root,
            year_component,
            f"{paper_id}.community.md",
            label="Community note path",
        )
        paper_title, pdf_path = _paper_context(vault, feed_root, paper_uid)
        rendered_notes.append(
            render_community_note(
                vault,
                paper_uid,
                list(all_items.values()),
                output,
                dry_run=dry_run,
                paper_title=paper_title,
                pdf_path=pdf_path,
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


def _paper_year(feed_root: Path, paper_uid: str, vault: Path | None = None) -> str:
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
    if vault is not None:
        source_id = paper_uid.split(":", 1)[-1]
        for note in sorted((vault / "10 Papers").rglob(f"{source_id}.md")):
            year = note.parent.name
            if re_full_year(year):
                return year
    return "Unclassified"


def re_full_year(value: str) -> bool:
    return len(value) == 4 and value.isdigit()


def render_community_note(vault: Path, paper_uid: str,
                          items: list[CommunityContribution],
                          output: Path, *, dry_run: bool = True,
                          paper_title: str = "", pdf_path: str = "") -> dict[str, Any]:
    visible = [item for item in items if item.paper_uid == paper_uid]
    title = paper_title or paper_uid
    metadata = {
        "type": "paperflow-community-note",
        "title": f"社区观点 · {title}",
        "aliases": [f"Community · {paper_uid.replace(':', '_')}"],
        "cssclasses": ["paperflow-community"],
        "paper_uid": paper_uid,
        "community_count": len(visible),
        "updated_at": iso_utc(),
    }
    lines = [
        dump_frontmatter(metadata).rstrip(), "", f"# 社区观点 · {title}", "",
        f"> {len(visible)} 条只读社区贡献；个人标注、评分和 AI 分析保持独立。", "",
        "## 贡献", "",
    ]
    for item in visible:
        label = _community_kind_label(item.kind)
        lines.extend([
            f"### {label} · @{item.creator}", "",
        ])
        if item.anchor and item.anchor.exact_quote:
            lines.extend([
                f"> [!quote] 原文摘录 · 第 {item.anchor.page} 页",
                f"> {_display_quote(item.anchor.exact_quote)}",
            ])
            if pdf_path:
                lines.extend(["", f"来源：[[{pdf_path}#page={item.anchor.page}|打开 PDF · 第 {item.anchor.page} 页]]"])
            lines.append("")
        if item.body.strip():
            lines.extend([item.body.strip(), ""])
        lines.extend([
            "> [!info]- 贡献信息",
            f"> 修订：r{item.revision} · 许可：{item.license}",
            f"> ID：`{item.contribution_id}`",
            "",
        ])
    if not dry_run:
        atomic_write(output, "\n".join(lines).rstrip() + "\n")
    return {"dry_run": dry_run, "path": output.relative_to(vault).as_posix(),
            "contributions": len(visible)}
