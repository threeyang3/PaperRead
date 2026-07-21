from __future__ import annotations

import json
from urllib.parse import quote

from paperflow.annotations.models import Annotation, PaperReview
from paperflow.obsidian.frontmatter import dump_frontmatter

START = "<!-- PAPERFLOW_ANNOTATION_START -->"
END = "<!-- PAPERFLOW_ANNOTATION_END -->"


def pdf_link(annotation: Annotation) -> str:
    anchor = annotation.preferred_revision.anchor
    fragment = f"page={anchor.page}"
    if anchor.text_quote_selector and anchor.text_quote_selector.exact:
        fragment += "&selection=" + quote(anchor.text_quote_selector.exact, safe="")
    return f"[[{anchor.pdf_path}#{fragment}]]"


def render_annotation(annotation: Annotation, unknown_markdown: str = "") -> str:
    revision = annotation.preferred_revision
    metadata = {
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
        "\n> " + selector.exact.replace("\n", "\n> ") + "\n"
        if selector and selector.exact else ""
    )
    preserved = unknown_markdown.rstrip()
    if preserved:
        preserved += "\n\n"
    return (
        dump_frontmatter(metadata) + "\n" + preserved
        + f"{START}\n<!-- {machine} -->\n"
        + f"## {annotation.kind}\n\n{pdf_link(annotation)}\n"
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
