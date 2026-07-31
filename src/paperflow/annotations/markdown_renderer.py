from __future__ import annotations

import json
from urllib.parse import quote

from paperflow.annotations.models import Annotation, PaperReview
from paperflow.obsidian.frontmatter import dump_frontmatter

START = "<!-- PAPERFLOW_ANNOTATION_START -->"
END = "<!-- PAPERFLOW_ANNOTATION_END -->"

KIND_LABELS = {
    "highlight": "高亮",
    "passage-comment": "段落评论",
    "question": "疑问",
    "critique": "批评",
    "figure-comment": "图评论",
    "section-comment": "章节评论",
    "paper-review": "论文评审",
    "rating": "评分",
}


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


def _display_quote(value: str) -> str:
    # The exact quote remains in the machine record; remove a leading colon
    # copied from a PDF title fragment from the reader-facing projection.
    return value.replace("\n", " ").strip().lstrip(":： ").strip()


def pdf_link(annotation: Annotation) -> str:
    anchor = annotation.preferred_revision.anchor
    fragment = f"page={anchor.page}"
    if anchor.pdf_selection:
        fragment += "&selection=" + quote(anchor.pdf_selection, safe=",")
        if anchor.highlight_color:
            fragment += "&color=" + quote(anchor.highlight_color, safe="")
    return f"[[{anchor.pdf_path}#{fragment}|打开 PDF · 第 {anchor.page} 页]]"


def render_annotation(annotation: Annotation, unknown_markdown: str = "") -> str:
    revision = annotation.preferred_revision
    label = kind_label(annotation.kind)
    metadata = {
        "title": f"标注 · {label}",
        "aliases": [f"{label} · {annotation.annotation_id}", annotation.annotation_id],
        "cssclasses": ["paperflow-annotation"],
        "annotation_id": annotation.annotation_id,
        "paper_uid": annotation.paper_uid,
        "kind": annotation.kind,
        "motivation": annotation.motivation,
        "created_at": annotation.created_at,
        "updated_at": annotation.updated_at,
        "reanchor_status": revision.status,
        "tags": annotation.tags,
    }
    machine = json.dumps(annotation.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    selector = revision.anchor.text_quote_selector
    quote_text = (
        "\n> [!quote] 原文摘录\n> " + _display_quote(selector.exact) + "\n"
        if selector and selector.exact else ""
    )
    preserved = unknown_markdown.rstrip()
    if preserved:
        preserved += "\n\n"
    return (
        dump_frontmatter(metadata) + "\n" + preserved
        + f"{START}\n<!-- {machine} -->\n"
        + f"## {label}\n\n来源：{pdf_link(annotation)}\n"
        + quote_text
        + ("\n" + annotation.body.strip() if annotation.body.strip() else "")
        + f"\n{END}\n"
    )


def render_review(review: PaperReview, unknown_markdown: str = "") -> str:
    metadata = review.model_dump(mode="json", exclude={"extensions"})
    sections = [
        ("摘要", review.summary), ("优点", review.strengths),
        ("局限", review.weaknesses), ("问题", review.questions),
        ("复现笔记", review.reproduction_notes), ("结论", review.verdict),
    ]
    return (
        dump_frontmatter(metadata) + "\n" + unknown_markdown.rstrip()
        + ("\n\n" if unknown_markdown.strip() else "")
        + "\n\n".join(f"## {name}\n\n{content}" for name, content in sections) + "\n"
    )
