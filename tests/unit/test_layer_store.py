from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperflow.data.records import AnalysisIdentity
from paperflow.data.store import load_reusable_analysis, persist_layer_records


def _record() -> dict:
    return {
        "paper_uid": "arxiv:2607.00001",
        "paper_source": "arxiv",
        "paper_arxiv_id": "2607.00001",
        "paper_arxiv_version": 1,
        "paper_title": "Immutable test",
        "ai_analysis_status": "complete",
        "ai_analysis_provider": "mock",
        "ai_analysis_model": "deterministic-v1",
        "ai_analysis_prompt_version": "paper-analysis-v2",
        "ai_summary_short": "analysis",
        "user_priority": 4,
        "system_content_hash": "abc",
    }


def test_persist_four_layers_and_reuse_identical_records(tmp_path: Path) -> None:
    paths = persist_layer_records(tmp_path, _record())
    again = persist_layer_records(tmp_path, _record())

    assert paths == again
    assert set(paths) == {"raw", "ai", "user", "derived"}
    raw = json.loads((tmp_path / paths["raw"]).read_text(encoding="utf-8"))
    assert all(not key.startswith(("ai_", "user_")) for key in raw["metadata"])


def test_raw_snapshot_cannot_be_overwritten(tmp_path: Path) -> None:
    persist_layer_records(tmp_path, _record())
    changed = _record()
    changed["paper_title"] = "Silently changed"

    with pytest.raises(RuntimeError, match="Immutable"):
        persist_layer_records(tmp_path, changed)


def test_reanalysis_preserves_existing_raw_but_writes_new_ai(tmp_path: Path) -> None:
    paths = persist_layer_records(tmp_path, _record())
    raw_path = tmp_path / paths["raw"]
    original_raw = raw_path.read_text(encoding="utf-8")
    changed = _record()
    changed["paper_title"] = "Verified display title"
    changed["ai_analysis_model"] = "new-model"
    changed["ai_summary_short"] = "New local analysis"

    updated = persist_layer_records(
        tmp_path,
        changed,
        preserve_existing_raw=True,
    )

    assert raw_path.read_text(encoding="utf-8") == original_raw
    assert "ai" in updated
    assert (tmp_path / updated["ai"]).is_file()


def test_identical_analysis_identity_is_reused(tmp_path: Path) -> None:
    paths = persist_layer_records(tmp_path, _record())
    stored = json.loads((tmp_path / paths["ai"]).read_text(encoding="utf-8"))
    identity = AnalysisIdentity.model_validate(stored["identity"])

    reused = load_reusable_analysis(
        tmp_path,
        paper_id="2607.00001",
        source_version=1,
        identity=identity,
    )
    assert reused is not None
    changed = identity.model_copy(update={"prompt_version": "changed"})
    assert (
        load_reusable_analysis(
            tmp_path,
            paper_id="2607.00001",
            source_version=1,
            identity=changed,
        )
        is None
    )
