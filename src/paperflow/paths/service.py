from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperflow.paths.templates import ALLOWED_VARIABLES, SafePathTemplate, resolve_inside
from paperflow.workspace import WorkspaceSettings


def record_variables(record: dict[str, Any], *, profile: str = "full_analysis") -> dict[str, Any]:
    submitted = str(record.get("paper_submitted_date") or "")
    return {
        "source": str(record.get("paper_source") or "arxiv"),
        "paper_id": str(record.get("paper_arxiv_id") or record.get("paper_uid", "")).replace(":", "_"),
        "arxiv_id": record.get("paper_arxiv_id", ""),
        "version": record.get("paper_arxiv_version", 1),
        "year": record.get("paper_year") or submitted[:4],
        "month": submitted[5:7] if len(submitted) >= 7 else "",
        "day": submitted[8:10] if len(submitted) >= 10 else "",
        "title": record.get("paper_title", ""),
        "first_author": record.get("paper_first_author", ""),
        "primary_category": record.get("paper_primary_category", ""),
        "category": record.get("paper_primary_category", ""),
        "categories": record.get("paper_categories", []),
        "type": record.get("paper_type") or "Paper",
        "primary_topic": record.get("ai_topic_primary", ""),
        "topics": record.get("ai_topics", []),
        "method_family": record.get("ai_method_family", []),
        "analysis_profile": profile,
        "analysis_id": record.get("analysis_id", ""),
        "date": submitted[:10],
    }


def preview_record_paths(
    root: Path,
    settings: WorkspaceSettings,
    record: dict[str, Any],
) -> dict[str, Any]:
    values = record_variables(
        record, profile=settings.ai.full_analysis_profile
    )
    result: dict[str, Any] = {
        "paper_uid": record.get("paper_uid", ""),
        "dependencies": {},
    }
    for name in ["raw_metadata", "ai_analysis", "user_data", "pdf", "note"]:
        rule = getattr(settings.paths, name)
        template = SafePathTemplate(
            rule.template,
            missing_value=settings.path_templates.missing_value,
            max_path_length=settings.path_templates.max_path_length,
        )
        relative = template.render(values)
        target = resolve_inside(root / rule.root, relative)
        old_key = {
            "pdf": "paper_pdf_path",
            "note": "note_path",
        }.get(name)
        old_path = record.get(old_key, "") if old_key else ""
        result[name] = {
            "old_path": old_path,
            "new_path": target.relative_to(root).as_posix(),
            "conflict": target.exists()
            and target.relative_to(root).as_posix() != old_path,
            "depends_on_ai": sorted(
                template.variables
                & {
                    "type",
                    "primary_topic",
                    "topics",
                    "method_family",
                    "analysis_profile",
                    "analysis_id",
                }
            ),
        }
    return result


def preview_all(root: Path, settings: WorkspaceSettings) -> list[dict[str, Any]]:
    legacy = root / ".paperflow/data/papers"
    return [
        preview_record_paths(
            root,
            settings,
            json.loads(path.read_text(encoding="utf-8")),
        )
        for path in sorted(legacy.glob("*.json"))
    ]


def validate_path_settings(root: Path, settings: WorkspaceSettings) -> list[str]:
    errors: list[str] = []
    for name, rule in settings.paths.model_dump().items():
        try:
            configured_root = resolve_inside(root, rule["root"])
            if rule.get("template"):
                SafePathTemplate(
                    rule["template"],
                    missing_value=settings.path_templates.missing_value,
                    max_path_length=settings.path_templates.max_path_length,
                )
            configured_root.relative_to(root.resolve())
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return errors


def variables_documentation() -> dict[str, str]:
    return {
        name: (
            "AI-derived; may use the configured missing value before analysis"
            if name
            in {
                "type",
                "primary_topic",
                "topics",
                "method_family",
                "analysis_profile",
                "analysis_id",
            }
            else "source metadata or run context"
        )
        for name in sorted(ALLOWED_VARIABLES)
    }
