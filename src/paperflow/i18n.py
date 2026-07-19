from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_LOCALES = {"zh-CN", "en"}


def normalize_locale(value: str | None) -> str:
    raw = (value or "").strip().replace("_", "-").lower()
    if raw.startswith("zh"):
        return "zh-CN"
    return "en"


@dataclass(frozen=True)
class LocaleInfo:
    locale: str
    source: str

    @property
    def is_chinese(self) -> bool:
        return self.locale == "zh-CN"


def resolve_locale(
    root: Path,
    configured: str | None = "auto",
    fallback: str | None = "zh-CN",
) -> LocaleInfo:
    configured_value = (configured or "auto").strip()
    if configured_value.lower() != "auto":
        return LocaleInfo(normalize_locale(configured_value), "paperflow.yaml")

    marker = root / ".paperflow/state/obsidian-locale.json"
    try:
        value = json.loads(marker.read_text(encoding="utf-8")).get("locale")
        if value:
            return LocaleInfo(normalize_locale(str(value)), "obsidian")
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        pass

    app_config = root / ".obsidian/app.json"
    try:
        data: dict[str, Any] = json.loads(app_config.read_text(encoding="utf-8"))
        value = data.get("language") or data.get("locale")
        if value:
            return LocaleInfo(normalize_locale(str(value)), "obsidian-app")
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        pass

    return LocaleInfo(normalize_locale(fallback), "fallback")


TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "validation.passed": "校验通过",
        "status.ui_locale": "界面语言",
        "status.ui_locale_source": "界面语言来源",
        "manual_review.title": "待人工合并",
        "manual_review.message": "原笔记缺少用户区标记，PaperFlow 未覆盖原文件。以下为建议的新版本：",
        "base.view.all_papers": "全部论文",
        "base.view.visual_gallery": "视觉浏览",
        "base.view.tactile_gallery": "触觉论文",
        "base.view.high_value_unread": "高价值未读",
        "base.view.recently_imported": "最近导入",
        "base.view.with_code": "有代码",
        "base.view.needs_manual_review": "需人工审核",
        "base.view.completed_reading": "已读完",
        "base.view.today": "今日导入",
        "base.view.reading_queue": "阅读队列",
        "base.view.reproduction_queue": "复现队列",
        "base.view.pending": "待处理",
        "base.view.processing": "处理中",
        "base.view.completed": "已完成",
        "base.view.failed": "失败",
        "property.paper_title": "论文标题",
        "property.paper_cover": "论文关键图",
        "property.paper_first_author": "第一作者",
        "property.paper_year": "年份",
        "property.ai_topic_primary": "主要主题",
        "property.ai_novelty_score": "创新性",
        "property.ai_completeness_score": "完成度",
        "property.ai_reproducibility_score": "可复现性",
        "property.ai_overall_score": "综合评分",
        "property.ai_summary_short": "一句话摘要",
        "property.user_reading_status": "阅读状态",
        "property.user_priority": "优先级",
        "property.paper_has_code": "有代码",
        "property.system_imported_at": "导入时间",
        "property.request_id": "请求 ID",
        "property.paper_input": "论文链接或 ID",
        "property.topic_hint": "主题提示",
        "property.priority": "优先级",
        "property.run_ai": "运行 AI",
        "property.ui_locale": "界面语言",
        "property.status": "状态",
        "property.created_at": "创建时间",
        "property.processed_at": "处理时间",
        "property.result_note": "结果笔记",
        "property.error": "错误",
    },
    "en": {
        "validation.passed": "Validation passed",
        "status.ui_locale": "ui_locale",
        "status.ui_locale_source": "ui_locale_source",
        "manual_review.title": "Manual merge required",
        "manual_review.message": "The original note has no protected user-note markers. PaperFlow did not overwrite it. Suggested new version:",
        "base.view.all_papers": "All Papers",
        "base.view.visual_gallery": "Visual Gallery",
        "base.view.tactile_gallery": "Tactile Papers",
        "base.view.high_value_unread": "High Value Unread",
        "base.view.recently_imported": "Recently Imported",
        "base.view.with_code": "With Code",
        "base.view.needs_manual_review": "Needs Manual Review",
        "base.view.completed_reading": "Completed Reading",
        "base.view.today": "Today",
        "base.view.reading_queue": "Reading Queue",
        "base.view.reproduction_queue": "Reproduction Queue",
        "base.view.pending": "Pending",
        "base.view.processing": "Processing",
        "base.view.completed": "Completed",
        "base.view.failed": "Failed",
        "property.paper_title": "Paper title",
        "property.paper_cover": "Key figure",
        "property.paper_first_author": "First author",
        "property.paper_year": "Year",
        "property.ai_topic_primary": "Primary topic",
        "property.ai_novelty_score": "Novelty",
        "property.ai_completeness_score": "Completeness",
        "property.ai_reproducibility_score": "Reproducibility",
        "property.ai_overall_score": "Overall score",
        "property.ai_summary_short": "One-line summary",
        "property.user_reading_status": "Reading status",
        "property.user_priority": "Priority",
        "property.paper_has_code": "Has code",
        "property.system_imported_at": "Imported at",
        "property.request_id": "Request ID",
        "property.paper_input": "Paper URL or ID",
        "property.topic_hint": "Topic hint",
        "property.priority": "Priority",
        "property.run_ai": "Run AI",
        "property.ui_locale": "UI language",
        "property.status": "Status",
        "property.created_at": "Created at",
        "property.processed_at": "Processed at",
        "property.result_note": "Result note",
        "property.error": "Error",
    },
}


def tr(locale: str, key: str, default: str | None = None) -> str:
    normalized = normalize_locale(locale)
    value = TRANSLATIONS.get(normalized, {}).get(key)
    if value is not None:
        return value
    if default is not None:
        return default
    return TRANSLATIONS["en"].get(key, key)
