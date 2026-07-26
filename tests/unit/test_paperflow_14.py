from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from paperflow.acceptance import _installed_distribution_files, _project_root
from paperflow.ai.chatgpt_web_adapter import _extract_json
from paperflow.cli import app
from paperflow.data.compose import compose_record
from paperflow.data.store import persist_layer_records
from paperflow.pipeline.visuals import CaptionCandidate, _select_candidates
from paperflow.relationships import derive_relationships
from paperflow.text_quality import (
    display_title,
    suspicious_text,
    validate_text_quality,
)
from paperflow.workspace import init_workspace


def _layer_record(title: str = r"$\pi_{0.5}$: Open-World Generalization") -> dict:
    return {
        "paper_uid": "arxiv:2504.16054",
        "paper_source": "arxiv",
        "paper_arxiv_id": "2504.16054",
        "paper_arxiv_version": 1,
        "paper_title": title,
        "ai_analysis_status": "complete",
        "ai_analysis_provider": "mock",
        "ai_analysis_model": "deterministic-v1",
        "ai_analysis_prompt_version": "paper-analysis-v3",
        "ai_summary_short": "分析",
        "user_priority": 4,
        "system_content_hash": "abc",
    }


def test_unicode_title_display_and_quality_guard() -> None:
    assert (
        display_title(r"$\pi_{0.5}$: a Vision-Language-Action Model")
        == "π₀.₅: a Vision-Language-Action Model"
    )
    assert not suspicious_text("π、中文、em—dash、α")
    with pytest.raises(ValueError, match="mojibake"):
        validate_text_quality({"analysis": "鏈锛"})


def test_changed_raw_is_appended_as_capture_when_explicit(tmp_path: Path) -> None:
    first = persist_layer_records(tmp_path, _layer_record())
    changed = _layer_record("π₀.₅: corrected source capture")
    second = persist_layer_records(
        tmp_path, changed, preserve_existing_raw=True
    )
    assert first["raw"].endswith("v1.json")
    assert "/v1/captures/" in second["raw"]
    assert (tmp_path / first["raw"]).is_file()
    assert (tmp_path / second["raw"]).is_file()


def test_compose_record_restores_derived_visual_assets(tmp_path: Path) -> None:
    derived = tmp_path / ".paperflow/data/derived/2504.16054.json"
    derived.parent.mkdir(parents=True)
    derived.write_text(
        json.dumps(
            {
                "derived": {
                    "extraction": {
                        "visual_assets": [
                            {"path": "80 Attachments/Papers/pi.assets/figure-1.png"}
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = compose_record(tmp_path, _layer_record())
    assert result["extraction"]["visual_assets"]
    assert result["paper_title_display"].startswith("π₀.₅")


def test_adaptive_visual_selection_can_return_zero_or_variable_count() -> None:
    low = CaptionCandidate(0, "1", "decorative sample", fitz.Rect(0, 0, 1, 1), "figure", 10)
    architecture = CaptionCandidate(
        0, "2", "System architecture overview", fitz.Rect(0, 0, 1, 1), "architecture", 110
    )
    result = CaptionCandidate(
        1, "3", "Benchmark result comparison", fitz.Rect(0, 0, 1, 1), "result", 80
    )
    assert _select_candidates([low], 12, quality_threshold=48) == []
    selected = _select_candidates(
        [low, architecture, result], 12, quality_threshold=48
    )
    assert [item.kind for item in selected] == ["architecture", "result"]
    assert len(_select_candidates([architecture, result], 1)) == 1


def test_relationship_index_separates_citations_and_semantic_links(
    tmp_path: Path,
) -> None:
    papers = tmp_path / ".paperflow/data/papers"
    papers.mkdir(parents=True)
    papers.joinpath("local.json").write_text(
        json.dumps(
            {
                "paper_uid": "arxiv:2301.00001",
                "paper_title": "Local Paper",
                "note_path": "10 Papers/2023/2301.00001.md",
                "ai_topics": ["Robotics"],
                "ai_method_family": ["Transformer"],
            }
        ),
        encoding="utf-8",
    )
    text = tmp_path / "paper.txt"
    text.write_text("References arXiv:2301.00001 and doi:10.1234/ABC.", encoding="utf-8")
    projected = derive_relationships(
        tmp_path,
        {
            "paper_uid": "arxiv:2504.16054",
            "paper_arxiv_id": "2504.16054",
            "ai_topics": ["Robotics"],
            "ai_method_family": ["Transformer"],
            "ai_datasets": [],
            "extraction": {"text_path": str(text)},
        },
    )
    assert projected["paper_cites"]
    assert "arxiv:2301.00001" not in projected["paper_citation_ids"]
    assert "doi:10.1234/abc" in projected["paper_citation_ids"]
    index = json.loads(
        (tmp_path / ".paperflow/data/relationships/2504.16054.json").read_text(
            encoding="utf-8"
        )
    )
    schema = json.loads(
        (Path(__file__).parents[2] / "schemas/paper-relationships.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(index)
    assert {edge["type"] for edge in index["edges"]} == {"citation", "semantic"}
    # Entity projections are maintained by an explicit command, not as a
    # side effect of every paper render/import.
    entity_files = list((tmp_path / "20 Topics").rglob("*.md"))
    assert entity_files
    assert all("PAPERFLOW_ENTITY_INDEX_START" not in path.read_text(encoding="utf-8") for path in entity_files)


def test_chatgpt_json_extractor_accepts_fenced_json_and_rejects_text() -> None:
    assert _extract_json('```json\n{"ok": true}\n```') == {"ok": True}
    with pytest.raises(ValueError):
        _extract_json("No structured result")


def test_acceptance_source_checks_are_independent_from_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = Path(__file__).parents[2].resolve()
    monkeypatch.chdir(repository)
    assert _project_root() == repository

    monkeypatch.chdir(tmp_path)
    assert _project_root() is None
    assert {
        "paperflow/resources/schemas/raw-paper.schema.json",
        "paperflow/resources/templates/Paper Note Template.md",
        "paperflow/resources/integrations/obsidian-paperflow-automation/main.js",
    } <= _installed_distribution_files()


def test_relationship_rebuild_has_safe_dry_run(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    init_workspace(vault)
    papers = vault / ".paperflow/data/papers"
    papers.mkdir(parents=True, exist_ok=True)
    papers.joinpath("2504.16054.json").write_text(
        json.dumps(
            {
                "paper_uid": "arxiv:2504.16054",
                "paper_title": r"$\pi_{0.5}$: Open-World Generalization",
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        ["rebuild-relationships", "--dry-run"],
        env={"PAPERFLOW_VAULT": str(vault)},
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "dry_run": True,
        "papers": ["arxiv:2504.16054"],
        "changes_applied": 0,
    }


def test_doctor_and_audit_accept_explicit_vault_from_source_checkout(
    tmp_path: Path,
) -> None:
    """Developer commands must not depend on the process cwd being the Vault."""
    vault = tmp_path / "vault"
    init_workspace(vault)
    doctor_result = CliRunner().invoke(app, ["doctor", "--vault", str(vault)])
    assert doctor_result.exit_code in {0, 1}
    assert "Traceback" not in (doctor_result.stdout or "")
    audit_result = CliRunner().invoke(app, ["audit", "--vault", str(vault)])
    # A minimal fixture may fail product checks, but it must execute the audit
    # and report evidence rather than fail during Vault discovery.
    assert audit_result.exit_code in {0, 1}
    assert "No PaperFlow Workspace found" not in (audit_result.stdout or "")
