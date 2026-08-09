from __future__ import annotations

import hashlib
import importlib
import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.config import load_config
from paperflow.models import PaperMetadata
from paperflow.obsidian.frontmatter import read_note, write_note
from paperflow.pipeline.inbox import process_inbox
from paperflow.workspace import default_workspace_dict, dump_yaml


PDF_BYTES = b"%PDF-1.4\n% PaperFlow deterministic golden workflow fixture\n%%EOF\n"
USER_NOTE_TEXT = "Golden workflow user note"


def _json(result) -> dict:
    assert result.exit_code == 0, result.stdout or repr(result.exception)
    return json.loads(result.stdout)


def _uid(source: str) -> str:
    match = re.search(r"(\d{4}\.\d{5})", source)
    assert match
    return f"arxiv:{match.group(1)}"


@pytest.fixture
def golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    import paperflow.cli as cli

    runner = CliRunner()
    vault = tmp_path / "vault"
    monkeypatch.setattr(cli, "try_install_official_plugin", lambda _root: {"status": "offline-test"})
    initialized = runner.invoke(
        app,
        ["init", "--vault", str(vault), "--non-interactive"],
    )
    assert initialized.exit_code == 0, initialized.stdout or repr(initialized.exception)

    workspace = default_workspace_dict()
    workspace["ai"]["profiles"]["full_analysis"]["provider"] = "mock"
    workspace["ai"]["profiles"]["full_analysis"]["fallback_profile"] = ""
    dump_yaml(vault / ".paperflow/workspace.yaml", workspace)

    importer = importlib.import_module("paperflow.pipeline.import_paper")
    counters = {"download": 0, "extract": 0}

    def metadata(_config, source: str) -> PaperMetadata:
        uid = _uid(source)
        paper_id = uid.split(":", 1)[1]
        return PaperMetadata(
            paper_uid=uid,
            paper_arxiv_id=paper_id,
            paper_title=f"Golden Embodied Intelligence Paper {paper_id}",
            paper_authors=["Test Author"],
            paper_first_author="Test Author",
            paper_year=2026,
            paper_abstract="Embodied intelligence robot learning fixture.",
            paper_pdf_url=f"https://fixtures.invalid/{paper_id}.pdf",
            paper_abs_url=source,
        )

    def download(_url: str, destination: Path, *_args) -> str:
        counters["download"] += 1
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(PDF_BYTES)
        return hashlib.sha256(destination.read_bytes()).hexdigest()

    def extract(_pdf: Path, output: Path) -> dict:
        counters["extract"] += 1
        text = "Abstract\nGolden workflow extracted text.\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        return {
            "text_path": str(output),
            "page_count": 1,
            "headings": ["Abstract"],
            "character_count": len(text),
        }

    monkeypatch.setattr(importer, "_metadata", metadata)
    monkeypatch.setattr(importer, "download_pdf", download)
    monkeypatch.setattr(importer, "extract_pdf", extract)
    monkeypatch.setattr(importer, "refresh_record_visuals", lambda *_args, **_kwargs: None)
    return {
        "runner": runner,
        "vault": vault,
        "importer": importer,
        "metadata": metadata,
        "counters": counters,
        "make_provider": importer.make_provider,
    }


def test_import_without_unmatched_topics_completes(golden: dict) -> None:
    source = "https://arxiv.org/abs/2601.00001"
    result = _json(
        golden["runner"].invoke(
            app,
            ["paper", "add", source, "--no-ai", "--vault", str(golden["vault"])],
        )
    )
    assert result["status"] == "imported"
    review = golden["vault"] / "50 Inbox/Manual Review/arxiv_2601.00001-topics.md"
    assert not review.exists()

    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", "arxiv:2601.00001", "--vault", str(golden["vault"])],
        )
    )
    assert inspected["raw"]["exists"] is True
    assert inspected["pdf"]["exists"] is True
    assert inspected["paper_hub"]["exists"] is True
    assert inspected["user_note"]["exists"] is True
    assert inspected["ai"]["exists"] is False
    assert inspected["ai"]["markdown_exists"] is False


def test_import_with_unmatched_topics_creates_manual_review(golden: dict) -> None:
    source = "https://arxiv.org/abs/2601.00002"
    result = _json(
        golden["runner"].invoke(
            app,
            [
                "paper",
                "add",
                source,
                "--no-ai",
                "--topic",
                "new-topic",
                "--vault",
                str(golden["vault"]),
            ],
        )
    )
    review = golden["vault"] / "50 Inbox/Manual Review/arxiv_2601.00002-topics.md"
    assert result["status"] == "imported"
    assert review.exists()
    review_text = review.read_text(encoding="utf-8")
    assert "paper_uid: arxiv:2601.00002" in review_text
    assert "new-topic" in review_text
    assert "status: pending" in review_text

    rendered = golden["runner"].invoke(
        app,
        ["paper", "render", "arxiv:2601.00002", "--vault", str(golden["vault"])],
    )
    assert rendered.exit_code == 0, rendered.stdout or repr(rendered.exception)
    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", "arxiv:2601.00002", "--vault", str(golden["vault"])],
        )
    )
    assert inspected["manual_review"] == {
        "required": True,
        "reasons": ["unmatched-topic"],
    }
    hub_frontmatter, _ = read_note(golden["vault"] / result["note_path"])
    assert hub_frontmatter["system_requires_manual_review"] is True


def test_golden_workflow_preserves_user_owned_artifacts(golden: dict) -> None:
    vault = golden["vault"]
    source = "https://arxiv.org/abs/2601.00003"
    uid = "arxiv:2601.00003"
    request = load_config(vault).path("request_folder") / "golden-request.md"
    write_note(
        request,
        {
            "type": "paper-import-request",
            "schema_version": 1,
            "request_id": "golden-request",
            "paper_input": source,
            "topic_hint": "",
            "priority": 3,
            "add_to_reading_queue": True,
            "favorite": False,
            "user_tags": [],
            "run_ai": True,
            "ui_locale": "en",
            "status": "pending",
            "created_at": "2026-08-09T10:00:00+08:00",
            "processed_at": None,
            "result_paper_uid": None,
            "result_note": None,
            "error": None,
        },
        f"# Paper import request\n\n## 用户备注\n\n{USER_NOTE_TEXT}\n",
    )
    assert process_inbox(load_config(vault)) == {"processed": 1, "failed": 0, "skipped": 0}

    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert inspected["raw"]["exists"] is True
    assert inspected["pdf"]["exists"] is True
    assert inspected["text"]["exists"] is True
    assert inspected["ai"]["exists"] is True
    assert inspected["ai"]["markdown_exists"] is True
    assert inspected["paper_hub"]["exists"] is True
    assert inspected["user_note"]["exists"] is True
    user_note = vault / inspected["user_note"]["path"]
    assert USER_NOTE_TEXT in user_note.read_text(encoding="utf-8")
    hub = vault / inspected["paper_hub"]["path"]
    assert inspected["user_note"]["path"].removesuffix(".md") in hub.read_text(encoding="utf-8")
    hub_frontmatter, hub_body = read_note(hub)
    hub_frontmatter["user_custom_golden"] = "preserve me"
    write_note(hub, hub_frontmatter, hub_body)

    created_review = _json(
        golden["runner"].invoke(
            app,
            ["review", "create", uid, "--vault", str(vault)],
        )
    )
    assert created_review["status"] == "created"
    review = vault / created_review["path"]
    review.write_text(
        review.read_text(encoding="utf-8") + "\n这是用户的重要 Review 内容\n",
        encoding="utf-8",
    )
    review_hash = hashlib.sha256(review.read_bytes()).hexdigest()
    review_id = created_review["review_id"]
    existing_review = _json(
        golden["runner"].invoke(
            app,
            ["review", "create", uid, "--vault", str(vault)],
        )
    )
    assert existing_review["status"] == "existing"
    assert existing_review["review_id"] == review_id
    assert hashlib.sha256(review.read_bytes()).hexdigest() == review_hash

    pdf_link = f"[[{inspected['pdf']['path']}#page=1]]"
    annotation = _json(
        golden["runner"].invoke(
            app,
            [
                "annotation",
                "create",
                uid,
                pdf_link,
                "--body",
                "Golden annotation",
                "--apply",
                "--vault",
                str(vault),
            ],
        )
    )
    annotation_path = vault / annotation["markdown"]
    annotation_hash = hashlib.sha256(annotation_path.read_bytes()).hexdigest()
    user_note_hash = hashlib.sha256(user_note.read_bytes()).hexdigest()

    def assert_user_owned_artifacts_unchanged() -> None:
        assert hashlib.sha256(user_note.read_bytes()).hexdigest() == user_note_hash
        assert hashlib.sha256(review.read_bytes()).hexdigest() == review_hash
        assert hashlib.sha256(annotation_path.read_bytes()).hexdigest() == annotation_hash
        current_frontmatter, _ = read_note(hub)
        assert current_frontmatter["user_custom_golden"] == "preserve me"

    analyzed = golden["runner"].invoke(
        app,
        ["paper", "analyze", uid, "--vault", str(vault)],
    )
    assert analyzed.exit_code == 0, analyzed.stdout or repr(analyzed.exception)
    assert_user_owned_artifacts_unchanged()
    rendered = golden["runner"].invoke(
        app,
        ["paper", "render", uid, "--vault", str(vault)],
    )
    assert rendered.exit_code == 0, rendered.stdout or repr(rendered.exception)
    assert_user_owned_artifacts_unchanged()
    refreshed = golden["runner"].invoke(
        app,
        ["paper", "refresh", uid, "--vault", str(vault)],
    )
    assert refreshed.exit_code == 0, refreshed.stdout or repr(refreshed.exception)
    assert_user_owned_artifacts_unchanged()
    duplicate = _json(
        golden["runner"].invoke(
            app,
            ["paper", "add", source, "--vault", str(vault)],
        )
    )
    assert duplicate["status"] == "skipped"
    assert duplicate["paper_uid"] == uid
    assert_user_owned_artifacts_unchanged()

    final = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert final["review"]["review_id"] == review_id
    assert final["annotations"]["count"] == 1


def test_ai_failure_is_inspectable_and_retry_reuses_local_artifacts(
    golden: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "https://arxiv.org/abs/2601.00004"
    uid = "arxiv:2601.00004"

    class FailingProvider:
        config = type("Config", (), {"model": "deterministic-v1"})()

        def analyze(self, *_args, **_kwargs):
            raise RuntimeError("deterministic mock AI failure")

    monkeypatch.setattr(golden["importer"], "make_provider", lambda *_args: FailingProvider())
    failed = golden["runner"].invoke(
        app,
        ["paper", "add", source, "--vault", str(golden["vault"])],
    )
    assert failed.exit_code != 0

    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(golden["vault"])],
        )
    )
    assert inspected["exists"] is True
    assert inspected["pdf"]["exists"] is True
    assert inspected["text"]["exists"] is True
    assert inspected["ai"]["status"] == "failed"
    assert inspected["job"]["status"] == "failed_retryable"
    counts_before_retry = dict(golden["counters"])

    monkeypatch.setattr(golden["importer"], "make_provider", golden["make_provider"])
    retried = golden["runner"].invoke(
        app,
        ["paper", "analyze", uid, "--vault", str(golden["vault"])],
    )
    assert retried.exit_code == 0, retried.stdout or repr(retried.exception)
    assert golden["counters"] == counts_before_retry
    final = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(golden["vault"])],
        )
    )
    assert final["ai"]["status"] == "complete"
    assert final["job"]["status"] == "completed"
