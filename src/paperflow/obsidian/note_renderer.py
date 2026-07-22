from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from paperflow.utils import atomic_write, iso_beijing, now_beijing
from paperflow.i18n import tr
from .frontmatter import preserve_user_fields, read_note, write_note
from paperflow.data.user_store import merge_user_data, save_user_record
from paperflow.relationships import derive_relationships
from paperflow.sync_safety import ExpectedFile
from paperflow.text_quality import display_title, title_aliases, user_display_title, short_title
from paperflow.obsidian.artifacts import ensure_ai_analysis_note, hub_links, MIGRATION_MARKER
from paperflow.obsidian.view_model import build_paper_view_model, PAPER_VIEW_MODEL_CONTEXT_VERSION
from paperflow.template_sets import TemplateSetManager

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
    env = SandboxedEnvironment(loader=FileSystemLoader(root / "90 System/Templates"), undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    template = "Paper Note Template.en.md" if ui_locale == "en" else "Paper Note Template.md"
    record["paper_title_display"] = display_title(
        str(record.get("paper_title") or note_path.stem)
    )
    record.update(derive_relationships(root, record))
    # Resolve user title and reading fields before rendering the view model;
    # the frontmatter projection is user-owned and must win over Raw/AI.
    seeded_frontmatter: dict[str, Any] = {}
    if note_path.exists():
        seeded_frontmatter, _ = read_note(note_path)
        record = {**record, **merge_user_data(root, record, seeded_frontmatter)}
    override_title = user_display_title(record)
    if override_title:
        record["paper_title_display"] = override_title
        record["paper_display_title"] = override_title
    record.setdefault("paper_short_title", short_title(str(record.get("paper_title") or note_path.stem)))
    try:
        from paperflow.workspace import load_workspace_settings
        _, settings = load_workspace_settings(root)
        context_record = {**record, "note_path": note_path.relative_to(root).as_posix()}
        template_values = build_paper_view_model(root, settings, context_record)
        template_values["links"] = hub_links(root, settings, context_record)
    except Exception:
        settings = None
        template_values = {
            "extraction": record.get("extraction") or {},
            "links": {"ai_analysis": "", "user_note": "", "annotations": "", "review": "", "community": ""},
            **record,
        }
    template_values.setdefault("extraction", record.get("extraction") or {})
    template_values.setdefault(
        "links",
        {"ai_analysis": "", "user_note": "", "annotations": "", "review": "", "community": ""},
    )
    # Keep the locale template as the complete AI artifact; the active
    # Template Set controls the compact Paper Hub projection.
    analysis_body = _compact_generated_markdown(
        env.get_template(template).render(**template_values)
    )
    body = analysis_body
    try:
        manager = TemplateSetManager(root)
        hub_path, _, _ = manager._find(manager.active_id())
        if (hub_path / "Paper Hub.md").exists():
            hub_env = SandboxedEnvironment(
                loader=FileSystemLoader(hub_path),
                undefined=StrictUndefined,
                autoescape=False,
                keep_trailing_newline=True,
            )
            body = _compact_generated_markdown(
                hub_env.get_template("Paper Hub.md").render(**template_values)
            )
    except Exception:
        pass
    if not note_path.exists() and not USER_RE.search(body):
        # Keep the legacy marker for newly created notes so older extensions
        # and the formal user-note migration can still recognize ownership.
        body = body.rstrip() + "\n\n<!-- USER_NOTES_START -->\n\n<!-- USER_NOTES_END -->\n"
    old_frontmatter: dict[str, Any] = {}
    expected = ExpectedFile.capture(note_path)
    if note_path.exists():
        old_frontmatter, old_body = read_note(note_path)
        notes = extract_user_notes(old_body)
        if notes is None and MIGRATION_MARKER not in old_body:
            review = root / "50 Inbox/Manual Review" / f"{note_path.stem}-merge-{now_beijing().strftime('%Y%m%d-%H%M%S')}.md"
            atomic_write(review, f"# {tr(ui_locale, 'manual_review.title')}\n\n{tr(ui_locale, 'manual_review.message')}\n\n" + body)
            raise RuntimeError(f"Unsafe merge refused; review {review.relative_to(root).as_posix()}")
        if notes is not None:
            preserved = f"<!-- USER_NOTES_START -->{notes}<!-- USER_NOTES_END -->"
            body = (
                USER_RE.sub(preserved, body)
                if USER_RE.search(body)
                else body.rstrip() + "\n\n" + preserved + "\n"
            )
        else:
            target = ""
            if settings is not None:
                target = hub_links(
                    root, settings, {**record, "note_path": note_path.relative_to(root).as_posix()}
                ).get("user_note", "")
            body = USER_RE.sub(
                f"## 用户笔记\n\n> 已迁移到 [[{target.removesuffix('.md')}]]。\n",
                body,
            )
            migration_line = next(
                (line.strip() for line in old_body.splitlines() if MIGRATION_MARKER in line),
                f"<!-- {MIGRATION_MARKER} -->",
            )
            if MIGRATION_MARKER not in body:
                body = body.rstrip() + "\n\n" + migration_line + "\n"
    merged_user = merge_user_data(root, record, old_frontmatter)
    record = {**record, **merged_user}
    values = {
        "type": "paper", "schema_version": 2, "system_template_version": 6,
        "system_template_context_version": PAPER_VIEW_MODEL_CONTEXT_VERSION,
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
    # Reaching this point means the note passed the merge and concurrent-write
    # guards.  Clear stale failure state left by an earlier manual-review
    # pause; otherwise a successfully migrated note would remain marked as
    # blocked in the Hub frontmatter forever.
    values["system_requires_manual_review"] = False
    values["system_error"] = ""
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
    if settings is not None:
        ensure_ai_analysis_note(
            root,
            settings,
            {**record, "note_path": note_path.relative_to(root).as_posix()},
            analysis_body,
            locale=ui_locale,
        )
    return note_path
