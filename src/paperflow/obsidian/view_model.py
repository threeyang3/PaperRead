from __future__ import annotations

"""Stable template context for Paper Workspace artifacts."""

from typing import Any

from paperflow.obsidian.artifacts import hub_links
from paperflow.text_quality import display_title, short_title, user_display_title

PAPER_VIEW_MODEL_CONTEXT_VERSION = 1


def build_paper_view_model(root, settings, record: dict[str, Any]) -> dict[str, Any]:
    source_title = str(record.get("paper_title") or record.get("paper_arxiv_id") or "Untitled")
    readable = display_title(source_title)
    override = user_display_title(record)
    paper = {
        "uid": record.get("paper_uid", ""),
        "id": record.get("paper_arxiv_id", ""),
        "source": record.get("paper_source", "arxiv"),
        "title": source_title,
        "display_title": override or readable,
        "short_title": record.get("paper_short_title") or short_title(source_title),
        "authors": record.get("paper_authors", []),
        "year": record.get("paper_year", ""),
        "abstract": record.get("paper_abstract", ""),
        "pdf_path": record.get("paper_pdf_path", ""),
    }
    analysis = {
        key.removeprefix("ai_"): value
        for key, value in record.items()
        if key.startswith("ai_")
    }
    user = {
        key.removeprefix("user_"): value
        for key, value in record.items()
        if key.startswith("user_")
    }
    links = hub_links(root, settings, record)
    model = {
        "context_version": PAPER_VIEW_MODEL_CONTEXT_VERSION,
        "paper": paper,
        "analysis": analysis,
        "user": user,
        "links": links,
        "visuals": (record.get("extraction") or {}).get("visual_assets", []),
        "relations": {
            "citations": record.get("paper_cites", []),
            "citation_ids": record.get("paper_citation_ids", []),
            "related": record.get("ai_related_papers", []),
            "topics": record.get("ai_topic_links", []),
            "methods": record.get("ai_method_links", []),
            "datasets": record.get("ai_dataset_links", []),
        },
        "provenance": {
            "provider": record.get("ai_analysis_provider", ""),
            "model": record.get("ai_analysis_model", ""),
            "prompt": record.get("ai_analysis_prompt_version", ""),
            "analyzed_at": record.get("ai_analyzed_at", ""),
        },
    }
    # Keep legacy flat keys for v6 templates and third-party custom templates.
    model.update(record)
    model["paper_title_display"] = paper["display_title"]
    model["paper_short_title"] = paper["short_title"]
    model["paper_display_title"] = paper["display_title"]
    model["system_template_context_version"] = PAPER_VIEW_MODEL_CONTEXT_VERSION
    return model
