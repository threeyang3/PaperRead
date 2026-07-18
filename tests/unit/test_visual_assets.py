from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
from jsonschema import validate

from paperflow.pipeline.visuals import (
    _caption_candidates,
    _crop_rectangle,
    _select_candidates,
    extract_visual_assets,
    refresh_record_visuals,
)
from paperflow.obsidian.note_renderer import render_paper
from paperflow.data.records import split_legacy_record
from paperflow.validation import validate_visual_assets
from paperflow.config import load_config
from paperflow.workspace import (
    init_workspace,
    install_workspace_resources,
    load_workspace_settings,
)


def _synthetic_paper(path: Path) -> None:
    document = fitz.open()
    architecture = document.new_page(width=600, height=800)
    architecture.draw_rect(fitz.Rect(70, 120, 220, 250), color=(0, 0, 0))
    architecture.draw_rect(fitz.Rect(370, 120, 520, 250), color=(0, 0, 0))
    architecture.draw_line((220, 185), (370, 185), color=(0, 0, 0))
    architecture.insert_textbox(
        fitz.Rect(60, 285, 540, 340),
        "Figure 1: Overview of the model architecture and training pipeline.",
        fontsize=11,
    )
    results = document.new_page(width=600, height=800)
    results.draw_rect(fitz.Rect(80, 140, 520, 330), color=(0, 0, 0))
    results.insert_textbox(
        fitz.Rect(60, 360, 540, 410),
        "Figure 2: Evaluation results and comparison across all tasks.",
        fontsize=11,
    )
    document.save(path)
    document.close()


def test_extract_visual_assets_prefers_architecture_and_writes_manifest(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "paper.pdf"
    _synthetic_paper(pdf)

    assets = extract_visual_assets(
        pdf,
        tmp_path / "paper.assets",
        root=tmp_path,
        paper_uid="arxiv:test",
        max_assets=2,
    )

    assert len(assets) == 2
    assert assets[0]["kind"] == "architecture"
    assert assets[0]["figure_number"] == "1"
    assert assets[0]["path"].startswith("paper.assets/")
    image = tmp_path / assets[0]["path"]
    assert image.is_file()
    assert assets[0]["sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
    manifest = json.loads(
        (tmp_path / "paper.assets/manifest.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        (
            Path(__file__).parents[2] / "schemas/visual-assets.schema.json"
        ).read_text(encoding="utf-8")
    )
    validate(manifest, schema)


def test_architecture_crop_prefers_complete_figure_width(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    _synthetic_paper(pdf)
    with fitz.open(pdf) as document:
        candidate = _caption_candidates(document)[0]
        crop = _crop_rectangle(document[candidate.page_index], candidate)

    assert crop.x0 <= 20
    assert crop.x1 >= 580
    assert crop.y0 <= 110
    assert crop.y1 >= 290


def test_visual_selection_preserves_architecture_and_result_coverage(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "coverage.pdf"
    document = fitz.open()
    for number, caption in enumerate(
        [
            "Model architecture and training pipeline.",
            "System overview for tactile manipulation.",
            "Framework design and inference workflow.",
            "Ablation results across tasks.",
            "Quantitative benchmark comparison.",
            "Robot setup and manipulation task.",
            "Additional qualitative examples.",
        ],
        start=1,
    ):
        page = document.new_page(width=600, height=800)
        page.draw_rect(fitz.Rect(60, 120, 540, 300), color=(0, 0, 0))
        page.insert_textbox(
            fitz.Rect(50, 330, 550, 390),
            f"Figure {number}: {caption}",
            fontsize=11,
        )
    document.save(pdf)
    document.close()

    with fitz.open(pdf) as opened:
        selected = _select_candidates(_caption_candidates(opened), 6)

    assert len(selected) == 6
    assert [item.kind for item in selected].count("architecture") == 3
    assert [item.kind for item in selected].count("result") == 2
    assert [item.kind for item in selected].count("figure") == 1


def test_refresh_record_visuals_keeps_assets_in_derived_pdf_directory(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "80 Attachments/Papers/2026/test.pdf"
    pdf.parent.mkdir(parents=True)
    _synthetic_paper(pdf)
    record = {
        "paper_uid": "arxiv:test",
        "paper_pdf_path": pdf.relative_to(tmp_path).as_posix(),
        "extraction": {"page_count": 2},
    }

    result = refresh_record_visuals(tmp_path, record, max_assets=1)

    assert result is record
    assert record["extraction"]["visual_extraction_status"] == "complete"
    assert len(record["extraction"]["visual_assets"]) == 1
    assert record["extraction"]["visual_assets"][0]["path"].startswith(
        "80 Attachments/Papers/2026/test.assets/"
    )


def test_extract_visual_assets_does_not_invent_uncaptioned_figures(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "plain.pdf"
    document = fitz.open()
    page = document.new_page()
    page.draw_rect(fitz.Rect(100, 100, 400, 300))
    document.save(pdf)
    document.close()

    assets = extract_visual_assets(
        pdf,
        tmp_path / "plain.assets",
        root=tmp_path,
        paper_uid="arxiv:plain",
    )

    assert assets == []


def test_visual_guide_renders_and_preserves_user_notes(tmp_path: Path) -> None:
    template_dir = tmp_path / "90 System/Templates"
    template_dir.mkdir(parents=True)
    source = Path(__file__).parents[2] / "templates/Paper Note Template.md"
    (template_dir / source.name).write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    record = {
        "paper_uid": "arxiv:test",
        "paper_title": "Test paper",
        "paper_authors": ["Ada"],
        "paper_arxiv_id": "test",
        "paper_abs_url": "https://arxiv.org/abs/test",
        "paper_pdf_path": "80 Attachments/Papers/test.pdf",
        "paper_project_url": "",
        "paper_code_url": "",
        "paper_dataset_url": "",
        "paper_has_code": False,
        "paper_has_dataset": False,
        "ai_summary_short": "Summary",
        "ai_topics": [],
        "ai_recommendation": "推荐",
        "ai_novelty_score": 4,
        "ai_novelty_reason": "Evidence",
        "ai_completeness_score": 4,
        "ai_completeness_reason": "Evidence",
        "ai_reproducibility_score": 3,
        "ai_reproducibility_reason": "Evidence",
        "ai_analysis_provider": "mock",
        "ai_analysis_model": "mock",
        "ai_analysis_prompt_version": "paper-analysis-v2",
        "ai_analyzed_at": "2026-07-18T12:00:00+08:00",
        "sections": {},
        "version_change_note": "v1",
        "extraction": {
            "visual_assets": [
                {
                    "figure_number": "1",
                    "kind": "architecture",
                    "caption": "Overview of the model architecture.",
                    "page": 2,
                    "path": "80 Attachments/Papers/test.assets/figure-1-p2.png",
                }
            ]
        },
    }
    note = tmp_path / "10 Papers/2026/test.md"

    render_paper(tmp_path, record, note, ui_locale="zh-CN")
    first = note.read_text(encoding="utf-8")
    assert "## 论文视觉导读" in first
    assert "![[80 Attachments/Papers/test.assets/figure-1-p2.png|950]]" in first
    assert "架构、系统与方法图" in first
    assert "已从原 PDF 提取 1 张可追溯关键图片" in first
    assert "[[80 Attachments/Papers/test.pdf#page=2|在原 PDF 中打开本页]]" in first
    note.write_text(
        first.replace(
            "<!-- USER_NOTES_START -->",
            "<!-- USER_NOTES_START -->\n\n我的不可覆盖笔记",
        ),
        encoding="utf-8",
    )

    render_paper(tmp_path, record, note, ui_locale="zh-CN")

    second = note.read_text(encoding="utf-8")
    assert "我的不可覆盖笔记" in second
    assert "system_template_version: 4" in second


def test_layer_paths_remain_rebuildable_derived_data() -> None:
    record = {
        "paper_uid": "arxiv:test",
        "paper_source": "arxiv",
        "paper_arxiv_id": "test",
        "paper_arxiv_version": 1,
        "layer_paths": {
            "raw": ".paperflow/data/raw/arxiv/test/v1.json",
            "derived": ".paperflow/data/derived/test.json",
        },
    }

    raw, _ai, _user, derived = split_legacy_record(record)

    assert "layer_paths" not in raw.extensions
    assert derived.derived["layer_paths"]["raw"].endswith("/v1.json")


def test_result_terms_override_generic_architecture_words() -> None:
    from paperflow.pipeline.visuals import _classify

    kind, score = _classify(
        "Ablation results for the fast-model architecture."
    )

    assert kind == "result"
    assert score < 100


def test_visual_validation_detects_tampered_asset(tmp_path: Path) -> None:
    pdf = tmp_path / "80 Attachments/Papers/2026/test.pdf"
    pdf.parent.mkdir(parents=True)
    _synthetic_paper(pdf)
    assets = extract_visual_assets(
        pdf,
        pdf.with_suffix(".assets"),
        root=tmp_path,
        paper_uid="arxiv:test",
        max_assets=1,
    )
    assert validate_visual_assets(tmp_path) == []

    (tmp_path / assets[0]["path"]).write_bytes(b"tampered")

    errors = validate_visual_assets(tmp_path)
    assert any("asset SHA256 mismatch" in error for error in errors)


def test_visual_migration_creates_full_workspace_backup(tmp_path: Path) -> None:
    from paperflow.cli import _apply_visual_assets_migration
    from ruamel.yaml import YAML

    init_workspace(tmp_path)
    _, settings = load_workspace_settings(tmp_path)
    install_workspace_resources(tmp_path, settings)
    workspace_path = tmp_path / ".paperflow/workspace.yaml"
    workspace = YAML(typ="safe").load(
        workspace_path.read_text(encoding="utf-8")
    )
    workspace["versions"]["templates"] = 2
    from paperflow.workspace import dump_yaml

    dump_yaml(workspace_path, workspace)

    result = _apply_visual_assets_migration(
        load_config(tmp_path),
        max_assets=3,
    )

    backup = tmp_path / str(result["backup"])
    assert (backup / "manifest.json").is_file()
    assert (
        backup
        / "files/90 System/Templates/Paper Note Template.md"
    ).is_file()
    migrated = YAML(typ="safe").load(
        workspace_path.read_text(encoding="utf-8")
    )
    assert migrated["versions"]["templates"] == 4
