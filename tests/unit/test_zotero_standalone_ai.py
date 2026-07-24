from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperflow.zotero.markdown import render_ai_projection
from paperflow.zotero.standalone_ai import analyze_standalone, load_current_analysis
from paperflow.zotero.store import ensure_layout


def _root(tmp_path: Path) -> Path:
    ensure_layout(tmp_path, force_standalone=True)
    (tmp_path / "data/papers").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.yaml").write_text(
        "schema_version: 1\nstore: paperflow-core\n"
        "analysis:\n  provider: mock\n  profile: full_analysis\n  model: deterministic-v1\n",
        encoding="utf-8",
    )
    (tmp_path / "data/papers/arxiv_2504.16054.json").write_text(
        json.dumps({
            "paper_uid": "arxiv:2504.16054",
            "paper_arxiv_id": "2504.16054",
            "paper_arxiv_version": 1,
            "paper_title": "π0.5: a Vision-Language-Action Model",
            "paper_authors": ["Physical Intelligence"],
            "paper_abstract": "A vision language action model for open-world generalization.",
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def test_standalone_ai_is_append_only_and_renders_projection(tmp_path: Path) -> None:
    root = _root(tmp_path)
    result = analyze_standalone(root, "arxiv:2504.16054")
    assert result["status"] == "written"
    assert result["artifact_permission"] == "AI_VERSIONED"
    assert (root / result["path"]).is_file()
    current = load_current_analysis(root, "arxiv:2504.16054")
    assert current and current["status"] == "complete"

    projection = render_ai_projection(root, "arxiv:2504.16054", target="zotero", apply_changes=True)
    assert projection["status"] == "written"
    note = root / "documents/zotero/arxiv_2504.16054.analysis.md"
    assert "Vision-Language-Action" in note.read_text(encoding="utf-8")
    reused = analyze_standalone(root, "arxiv:2504.16054")
    assert reused["status"] == "reused"
    assert not (root / ".paperflow").exists()


def test_standalone_ai_rejects_unknown_provider(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "config.yaml").write_text(
        "schema_version: 1\nanalysis:\n  provider: local-unknown\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unsupported standalone provider"):
        analyze_standalone(root, "arxiv:2504.16054")


def test_standalone_ai_provider_config_is_used_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    (root / "config.yaml").write_text(
        "schema_version: 1\n"
        "analysis:\n"
        "  provider: claude\n"
        "  profile: full_analysis\n"
        "  model: claude-test\n"
        "  providers:\n"
        "    claude:\n"
        "      executable: claude-test\n"
        "      timeout_seconds: 42\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, int, str]] = []

    class FakeAdapter:
        def analyze(self, metadata, text_path):
            calls.append((str(text_path), metadata.paper_uid, text_path.read_text(encoding="utf-8")))
            from paperflow.ai.mock_adapter import MockAdapter

            return MockAdapter().analyze(metadata, text_path)

    def fake_factory(root_arg, policy, provider, model):
        assert root_arg == root.resolve()
        assert provider == "claude"
        assert model == "claude-test"
        assert policy["providers"]["claude"]["executable"] == "claude-test"
        return FakeAdapter()

    monkeypatch.setattr(
        "paperflow.zotero.standalone_ai._make_standalone_adapter", fake_factory
    )
    result = analyze_standalone(root, "arxiv:2504.16054")
    assert result["provider"] == "claude"
    assert calls and "Vision-Language-Action" in calls[0][2]


def test_standalone_ai_stages_pdf_text_when_zotero_pdf_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    pdf = root / "documents/zotero/2504.16054.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "PDF-only method evidence")
    document.save(pdf)
    document.close()
    captured: list[str] = []

    class FakeAdapter:
        def analyze(self, metadata, text_path):
            captured.append(text_path.read_text(encoding="utf-8"))
            from paperflow.ai.mock_adapter import MockAdapter

            return MockAdapter().analyze(metadata, text_path)

    monkeypatch.setattr(
        "paperflow.zotero.standalone_ai._make_standalone_adapter",
        lambda *_args: FakeAdapter(),
    )
    analyze_standalone(root, "arxiv:2504.16054", force=True)
    assert captured and "PDF-only method evidence" in captured[0]
