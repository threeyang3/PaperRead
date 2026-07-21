from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from paperflow.annotations.anchors import parse_pdf_link
from paperflow.annotations.markdown_parser import parse_annotation
from paperflow.annotations.markdown_renderer import render_annotation
from paperflow.annotations.models import Annotation, AnnotationRevision
from paperflow.annotations.reanchor import reanchor_quote
from paperflow.annotations.store import AnnotationStore
from paperflow.workspace import WorkspaceSettings, default_workspace_dict


def _pdf(vault: Path, version: int = 1) -> Path:
    path = vault / f"80 Attachments/Papers/2026/2607.00001/v{version}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.7\nfixture")
    return path


def _annotation(vault: Path) -> Annotation:
    pdf = _pdf(vault)
    anchor = parse_pdf_link(
        "[[80 Attachments/Papers/2026/2607.00001/v1.pdf#page=7&selection=robot%20policy]]",
        vault=vault,
        pdf_version=1,
    )
    return Annotation(
        annotation_id="ann-test",
        paper_uid="arxiv:2607.00001",
        kind="passage-comment",
        motivation="commenting",
        body="Private note",
        created_at="2026-07-20T10:00:00+08:00",
        updated_at="2026-07-20T10:00:00+08:00",
        revisions=[AnnotationRevision(
            revision=1, anchor=anchor,
            created_at="2026-07-20T10:00:00+08:00",
        )],
    )


def test_pdf_plus_and_native_link_round_trip(tmp_path: Path) -> None:
    annotation = _annotation(tmp_path)
    store = AnnotationStore(
        tmp_path, "60 Annotations", ".paperflow/data/user/annotations"
    )
    result = store.save(annotation)
    markdown = tmp_path / result["markdown"]
    parsed, _ = parse_annotation(markdown)
    assert parsed == annotation
    assert "page=7&selection=robot%20policy" in markdown.read_text(encoding="utf-8")
    assert parsed.preferred_revision.anchor.pdf_sha256 == hashlib.sha256(
        _pdf(tmp_path).read_bytes()
    ).hexdigest()


def test_unknown_markdown_is_preserved_and_markdown_wins(tmp_path: Path) -> None:
    annotation = _annotation(tmp_path)
    store = AnnotationStore(
        tmp_path, "60 Annotations", ".paperflow/data/user/annotations"
    )
    result = store.save(annotation)
    markdown = tmp_path / result["markdown"]
    markdown.write_text(
        "My unstructured preface\n\n" + markdown.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    store.save(annotation)
    assert "My unstructured preface" in markdown.read_text(encoding="utf-8")


def test_selector_validation_and_page_fallback(tmp_path: Path) -> None:
    _pdf(tmp_path)
    page = parse_pdf_link(
        "[[80 Attachments/Papers/2026/2607.00001/v1.pdf#page=3]]",
        vault=tmp_path,
        pdf_version=1,
    )
    assert page.page == 3
    assert page.text_quote_selector is None
    with pytest.raises(ValueError, match="escapes"):
        parse_pdf_link("[[../outside.pdf#page=1]]", vault=tmp_path, pdf_version=1)


def test_reanchor_strategy_matrix() -> None:
    assert reanchor_quote("same", "same", "same").status == "exact-selection-match"
    assert reanchor_quote("old", "prefix exact suffix", "exact").status == "exact-text-match"
    assert reanchor_quote("old", "prefix exact suffix", "exact", prefix="prefix ").method == "exact-text"
    fuzzy = reanchor_quote("old", "The robotic policx is stable", "robotic policy")
    assert fuzzy.status in {"quote-reanchored", "manual-review"}
    assert reanchor_quote("old", "none", "").status == "page-only"
    assert reanchor_quote("old", "none", "missing").status == "manual-review"
