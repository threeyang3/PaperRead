from __future__ import annotations
from pathlib import Path
from ruamel.yaml import YAML
from paperflow.i18n import resolve_locale, tr
from paperflow.utils import atomic_write

COLUMNS = ["paper_title", "paper_first_author", "paper_year", "ai_topic_primary", "ai_novelty_score", "ai_completeness_score", "ai_reproducibility_score", "ai_overall_score", "user_reading_status", "user_priority", "paper_has_code", "system_imported_at"]
REQUEST_COLUMNS = ["request_id", "paper_input", "topic_hint", "priority", "run_ai", "ui_locale", "status", "created_at", "processed_at", "result_note", "error"]


def _properties(locale: str, columns: list[str]) -> dict:
    return {name: {"displayName": tr(locale, f"property.{name}", name)} for name in columns}


def _base(
    views: list[dict],
    locale: str,
    request: bool = False,
    paper_root: str = "10 Papers",
    request_roots: tuple[str, str, str] = (
        "50 Inbox/Paper Requests",
        "50 Inbox/Processed Requests",
        "50 Inbox/Failed Imports",
    ),
) -> dict:
    filters = (
        {"or": [f'file.inFolder("{folder}")' for folder in request_roots]}
        if request
        else f'type == "paper" && file.inFolder("{paper_root}")'
    )
    columns = REQUEST_COLUMNS if request else COLUMNS
    return {"filters": filters, "properties": _properties(locale, columns), "views": views}


def definitions(
    locale: str = "zh-CN",
    *,
    paper_root: str = "10 Papers",
    request_roots: tuple[str, str, str] = (
        "50 Inbox/Paper Requests",
        "50 Inbox/Processed Requests",
        "50 Inbox/Failed Imports",
    ),
) -> dict[str, dict]:
    table = lambda key, filt=None, sort=None: {"type": "table", "name": tr(locale, f"base.view.{key}"), **({"filters": filt} if filt else {}), "order": COLUMNS, **({"sort": sort} if sort else {})}
    return {
        "Paper Library.base": _base([
            table("all_papers"), table("high_value_unread", 'ai_overall_score >= 4 && user_reading_status != "read"'),
            table("recently_imported", 'system_imported_at >= now() - "7d"', [{"property": "system_imported_at", "direction": "DESC"}]), table("with_code", "paper_has_code == true"),
            table("needs_manual_review", "system_requires_manual_review == true"), table("completed_reading", 'user_reading_status == "read"'),
        ], locale, paper_root=paper_root, request_roots=request_roots),
        "Daily Intake.base": _base([table("today", 'system_imported_at >= now() - "1d"', [{"property": "system_imported_at", "direction": "DESC"}])], locale, paper_root=paper_root, request_roots=request_roots),
        "Reading Queue.base": _base([table("reading_queue", 'user_reading_status == "queued" || user_reading_status == "reading"', [{"property": "user_priority", "direction": "DESC"}, {"property": "ai_overall_score", "direction": "DESC"}])], locale, paper_root=paper_root, request_roots=request_roots),
        "Reproduction Queue.base": _base([table("reproduction_queue", 'user_reproduction_status == "candidate" || user_reproduction_status == "planned" || user_reproduction_status == "in_progress"')], locale, paper_root=paper_root, request_roots=request_roots),
        "Paper Requests.base": _base([{"type": "table", "name": tr(locale, f"base.view.{name}"), "filters": f'status == "{name}"', "order": REQUEST_COLUMNS} for name in ["pending", "processing", "completed", "failed"]], locale, True, paper_root=paper_root, request_roots=request_roots),
    }


def rebuild_bases(
    root: Path,
    locale: str | None = None,
    *,
    base_root: str = "00 Dashboard/Bases",
    paper_root: str = "10 Papers",
    request_roots: tuple[str, str, str] = (
        "50 Inbox/Paper Requests",
        "50 Inbox/Processed Requests",
        "50 Inbox/Failed Imports",
    ),
) -> list[Path]:
    yaml = YAML()
    yaml.default_flow_style = False
    import io
    paths = []
    active_locale = locale or resolve_locale(root).locale
    for name, value in definitions(
        active_locale, paper_root=paper_root, request_roots=request_roots
    ).items():
        stream = io.StringIO(); yaml.dump(value, stream)
        path = root / base_root / name
        atomic_write(path, stream.getvalue()); paths.append(path)
    return paths


def validate_bases(
    root: Path,
    *,
    base_root: str = "00 Dashboard/Bases",
    paper_root: str = "10 Papers",
) -> list[str]:
    yaml = YAML(typ="safe"); errors = []
    for name in definitions(paper_root=paper_root):
        path = root / base_root / name
        try:
            value = yaml.load(path.read_text(encoding="utf-8"))
            if not value.get("views"): errors.append(f"{name}: no views")
        except Exception as exc: errors.append(f"{name}: {exc}")
    return errors
