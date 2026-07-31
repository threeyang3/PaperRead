from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paperflow.annotations.anchors import parse_pdf_link
from paperflow.annotations.markdown_parser import parse_annotation
from paperflow.annotations.markdown_renderer import render_annotation
from paperflow.annotations.models import Annotation, AnnotationRevision
from paperflow.annotations.reanchor import reanchor_quote
from paperflow.annotations.service import AnnotationService
from paperflow.annotations.store import AnnotationStore
from paperflow.cli import app
from paperflow.workspace import WorkspaceSettings, default_workspace_dict, init_workspace


def _pdf(vault: Path, version: int = 1) -> Path:
    path = vault / f"80 Attachments/Papers/2026/2607.00001/v{version}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.7\nfixture")
    return path


def _annotation(vault: Path) -> Annotation:
    pdf = _pdf(vault)
    anchor = parse_pdf_link(
        "[[80 Attachments/Papers/2026/2607.00001/v1.pdf#page=7&selection=12,0,14,38&color=yellow]]",
        vault=vault,
        pdf_version=1,
        selected_text="robot policy",
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
    rendered = markdown.read_text(encoding="utf-8")
    assert "page=7&selection=12,0,14,38&color=yellow" in rendered
    assert "## 段落评论" in rendered
    assert "来源：[[80 Attachments/Papers/2026/2607.00001/v1.pdf#page=7&selection=12,0,14,38&color=yellow|打开 PDF · 第 7 页]]" in rendered
    assert "> robot policy" in rendered
    assert parsed.preferred_revision.anchor.pdf_selection == "12,0,14,38"
    assert parsed.preferred_revision.anchor.highlight_color == "yellow"
    assert parsed.preferred_revision.anchor.pdf_sha256 == hashlib.sha256(
        _pdf(tmp_path).read_bytes()
    ).hexdigest()


def test_pdf_plus_html_escaped_query_is_normalized(tmp_path: Path) -> None:
    _pdf(tmp_path)
    anchor = parse_pdf_link(
        "[[80 Attachments/Papers/2026/2607.00001/v1.pdf#page=1&amp;selection=4,0,5,25&amp;color=yellow]]",
        vault=tmp_path,
        pdf_version=1,
        selected_text="actual quote",
    )
    assert anchor.page == 1
    assert anchor.pdf_selection == "4,0,5,25"
    assert anchor.highlight_color == "yellow"


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
    quoted_page = parse_pdf_link(
        "[[80 Attachments/Papers/2026/2607.00001/v1.pdf#page=3]]",
        vault=tmp_path,
        pdf_version=1,
        selected_text="manual visible text",
    )
    manual = _annotation(tmp_path).model_copy(deep=True)
    manual.revisions[0].anchor = quoted_page
    rendered = render_annotation(manual)
    assert "> manual visible text" in rendered
    assert "selection=" not in rendered
    with pytest.raises(ValueError, match="escapes"):
        parse_pdf_link("[[../outside.pdf#page=1]]", vault=tmp_path, pdf_version=1)


def test_annotation_service_rebuilds_private_index_after_create(tmp_path: Path) -> None:
    _pdf(tmp_path)
    settings = WorkspaceSettings.model_validate(default_workspace_dict())
    result = AnnotationService(tmp_path, settings).create(
        "arxiv:2607.00001",
        "[[80 Attachments/Papers/2026/2607.00001/v1.pdf#page=2&selection=1,2,3,4]]",
        pdf_version=1,
        kind="question",
        motivation="questioning",
        selected_text="Why this assumption?",
        body="Check the appendix.",
    )
    assert result["index"]["annotations"] == 1
    index = tmp_path / settings.paths.user_annotations.root / "index.json"
    assert index.exists()
    visible = tmp_path / "60 Annotations/arxiv_2607.00001/index.md"
    assert visible.exists()
    assert result["index"]["paper_indexes"][0]["path"] == (
        "60 Annotations/arxiv_2607.00001/index.md"
    )
    assert "ann-" in visible.read_text(encoding="utf-8")


def test_annotation_index_preserves_user_content_and_legacy_scaffolds(tmp_path: Path) -> None:
    annotation = _annotation(tmp_path)
    store = AnnotationStore(
        tmp_path, "Private Notes/Annotations", ".paperflow/data/user/annotations"
    )
    canonical = store.index_path(annotation.paper_uid)
    canonical.parent.mkdir(parents=True)
    canonical.write_text(
        "---\ntype: paperflow-annotation-index-note\npaper_uid: arxiv:2607.00001\n"
        "user_view: compact\n---\n\nMy pinned annotation note.\n",
        encoding="utf-8",
    )
    legacy_empty = (
        tmp_path / "Private Notes/Annotations/2026/arxiv_2607.00001/index.md"
    )
    legacy_empty.parent.mkdir(parents=True)
    legacy_empty.write_text(
        "---\ntype: paperflow-annotation-index-note\npaper_uid: arxiv:2607.00001\n"
        "---\n\n# 标注\n\nPDF++ 复制的标注链接可粘贴到这里；正式标注由 PaperFlow 命令同步。\n",
        encoding="utf-8",
    )
    legacy_user = (
        tmp_path / "Private Notes/Annotations/Archive/arxiv_2607.00001/index.md"
    )
    legacy_user.parent.mkdir(parents=True)
    legacy_user.write_text(
        "---\ntype: paperflow-annotation-index-note\npaper_uid: arxiv:2607.00001\n"
        "---\n\n# 标注\n\nMy legacy observation.\n",
        encoding="utf-8",
    )
    empty_before = legacy_empty.read_bytes()
    user_before = legacy_user.read_bytes()
    store.save(annotation)
    first = store.rebuild_paper_index(annotation.paper_uid, [annotation])
    second = store.rebuild_paper_index(annotation.paper_uid, [annotation])
    content = canonical.read_text(encoding="utf-8")
    assert first["path"] == "Private Notes/Annotations/arxiv_2607.00001/index.md"
    assert first["legacy_user_sections_imported"] == 1
    assert second["legacy_user_sections_imported"] == 0
    assert content.count("My pinned annotation note.") == 1
    assert content.count("My legacy observation.") == 1
    assert content.count("PAPERFLOW_ANNOTATION_INDEX_START") == 1
    assert "user_view: compact" in content
    assert legacy_empty.read_bytes() == empty_before
    assert legacy_user.read_bytes() == user_before


def test_annotation_cli_accepts_quote_separately_and_applies(tmp_path: Path) -> None:
    init_workspace(tmp_path)
    _pdf(tmp_path)
    result = CliRunner().invoke(app, [
        "annotation", "create", "arxiv:2607.00001",
        "[[80 Attachments/Papers/2026/2607.00001/v1.pdf#page=5&selection=2,3,4,5]]",
        "--kind", "highlight", "--motivation", "highlighting",
        "--selected-text", "actual selected text", "--pdf-version", "1",
        "--apply", "--vault", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    assert '"annotations": 1' in result.output
    notes = list((tmp_path / "60 Annotations").rglob("*.annotation.md"))
    assert len(notes) == 1
    content = notes[0].read_text(encoding="utf-8")
    assert "selection=2,3,4,5" in content
    assert "> actual selected text" in content


def test_reanchor_strategy_matrix() -> None:
    assert reanchor_quote("same", "same", "same").status == "exact-selection-match"
    assert reanchor_quote("old", "prefix exact suffix", "exact").status == "exact-text-match"
    assert reanchor_quote("old", "prefix exact suffix", "exact", prefix="prefix ").method == "exact-text"
    fuzzy = reanchor_quote("old", "The robotic policx is stable", "robotic policy")
    assert fuzzy.status in {"quote-reanchored", "manual-review"}
    assert reanchor_quote("old", "none", "").status == "page-only"
    assert reanchor_quote("old", "none", "missing").status == "manual-review"
