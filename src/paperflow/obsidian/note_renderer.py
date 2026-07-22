from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from paperflow.utils import atomic_write, iso_beijing, now_beijing
from paperflow.i18n import tr
from .frontmatter import preserve_user_fields, read_note, write_note
from paperflow.data.user_store import merge_user_data, save_user_record
from paperflow.relationships import derive_relationships
from paperflow.sync_safety import ExpectedFile
from paperflow.text_quality import display_title, title_aliases

USER_RE = re.compile(r"<!-- USER_NOTES_START -->(.*?)<!-- USER_NOTES_END -->", re.S)
NARRATIVE_FRONTMATTER_FIELDS = {
    "ai_relevance_reason",
    "ai_novelty_reason",
    "ai_completeness_reason",
    "ai_reproducibility_reason",
    "ai_recommendation",
}


def extract_user_notes(body: str) -> str | None:
    match = USER_RE.search(body)
    return match.group(1) if match else None


def _compact_generated_markdown(body: str) -> str:
    """Keep generated notes readable without touching preserved user prose."""
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", body).strip() + "\n"


def render_paper(root: Path, record: dict[str, Any], note_path: Path, import_method: str = "daily", ui_locale: str = "zh-CN") -> Path:
    env = Environment(loader=FileSystemLoader(root / "90 System/Templates"), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    template = "Paper Note Template.en.md" if ui_locale == "en" else "Paper Note Template.md"
    template_values = {"extraction": {}, **record}
    record["paper_title_display"] = display_title(
        str(record.get("paper_title") or note_path.stem)
    )
    record.update(derive_relationships(root, record))
    template_values = {"extraction": {}, **record}
    body = _compact_generated_markdown(env.get_template(template).render(**template_values))
    old_frontmatter: dict[str, Any] = {}
    expected = ExpectedFile.capture(note_path)
    if note_path.exists():
        old_frontmatter, old_body = read_note(note_path)
        notes = extract_user_notes(old_body)
        if notes is None:
            review = root / "50 Inbox/Manual Review" / f"{note_path.stem}-merge-{now_beijing().strftime('%Y%m%d-%H%M%S')}.md"
            atomic_write(review, f"# {tr(ui_locale, 'manual_review.title')}\n\n{tr(ui_locale, 'manual_review.message')}\n\n" + body)
            raise RuntimeError(f"Unsafe merge refused; review {review.relative_to(root).as_posix()}")
        body = USER_RE.sub(
            f"<!-- USER_NOTES_START -->{notes}<!-- USER_NOTES_END -->",
            body,
        )
    merged_user = merge_user_data(root, record, old_frontmatter)
    record = {**record, **merged_user}
    values = {
        "type": "paper", "schema_version": 2, "system_template_version": 6,
        "title": record["paper_title_display"],
        "aliases": title_aliases(record), "tags": ["paper"],
        **{
            k: v
            for k, v in record.items()
            if k.startswith(("paper_", "ai_", "user_", "system_"))
            and k not in NARRATIVE_FRONTMATTER_FIELDS
        },
    }
    values.setdefault("user_reading_status", "inbox")
    values.setdefault("user_learning_status", "none")
    values.setdefault("user_priority", 3)
    values.setdefault("user_favorite", False)
    values.setdefault("user_rating", 0)
    values.setdefault("user_reproduction_status", "none")
    values.setdefault("user_added_tags", [])
    values.setdefault("user_last_read_at", None)
    values.setdefault("user_next_review_at", None)
    values.setdefault("paper_has_code", bool(record.get("paper_code_url")))
    values.setdefault(
        "paper_has_project_page",
        bool(record.get("paper_project_url")),
    )
    values.setdefault("paper_has_dataset", bool(record.get("paper_dataset_url")))
    values.setdefault("system_import_method", import_method)
    values.setdefault("system_imported_at", iso_beijing())
    if old_frontmatter.get("system_imported_at"):
        values["system_imported_at"] = old_frontmatter["system_imported_at"]
    values["system_last_synced_at"] = iso_beijing()
    values.setdefault("system_pipeline_version", "0.1.0")
    values.setdefault("system_requires_manual_review", False)
    values.setdefault("system_error", "")
    values = preserve_user_fields(values, old_frontmatter)
    save_user_record(root, record, values)
    try:
        expected.assert_unchanged()
    except RuntimeError:
        review = (
            root
            / "50 Inbox/Manual Review"
            / f"{note_path.stem}-sync-conflict-"
            f"{now_beijing().strftime('%Y%m%d-%H%M%S')}.md"
        )
        atomic_write(
            review,
            "# 同步并发冲突\n\n"
            "PaperFlow 在写入前检测到笔记已被外部同步修改，因此拒绝覆盖。"
            "下面保留本次拟生成版本，请人工合并。\n\n"
            + body,
        )
        raise
    write_note(note_path, values, body)
    return note_path
