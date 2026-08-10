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
from paperflow.data.user_store import load_user_record, merge_and_save_user_record
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


def _write_form_flow_request(
    vault: Path,
    *,
    request_id: str,
    source: str,
    note: str,
    run_ai: bool = True,
    topic_hint: str = "",
    priority: int = 3,
    queued: bool = True,
    favorite: bool = False,
    user_tags: list[str] | None = None,
) -> Path:
    request = load_config(vault).path("request_folder") / f"{request_id}.md"
    write_note(
        request,
        {
            "type": "paper-import-request",
            "schema_version": 1,
            "request_id": request_id,
            "paper_input": source,
            "topic_hint": topic_hint,
            "priority": priority,
            "add_to_reading_queue": queued,
            "favorite": favorite,
            "user_tags": user_tags or [],
            "run_ai": run_ai,
            "ui_locale": "en",
            "status": "pending",
            "created_at": "2026-08-10T10:00:00+08:00",
            "processed_at": None,
            "result_paper_uid": None,
            "result_note": None,
            "error": None,
        },
        f"# Paper import request\n\n## 用户备注\n\n{note}\n",
    )
    return request


class FailingProvider:
    config = type("Config", (), {"model": "deterministic-v1"})()

    def analyze(self, *_args, **_kwargs):
        raise RuntimeError("deterministic mock AI failure")


@pytest.fixture
def golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    import paperflow.cli as cli

    runner = CliRunner()
    vault = tmp_path / "vault"
    monkeypatch.setattr(
        cli, "try_install_official_plugin", lambda _root: {"status": "offline-test"}
    )
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


def test_duplicate_form_flow_request_preserves_new_user_note(golden: dict) -> None:
    vault = golden["vault"]
    source = "https://arxiv.org/abs/2601.00005"
    uid = "arxiv:2601.00005"
    initial = _json(
        golden["runner"].invoke(
            app,
            ["paper", "add", source, "--no-ai", "--vault", str(vault)],
        )
    )
    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    user_note = vault / inspected["user_note"]["path"]
    user_note.write_text(
        user_note.read_text(encoding="utf-8") + "\nORIGINAL USER NOTE\n",
        encoding="utf-8",
    )

    second = _write_form_flow_request(
        vault,
        request_id="second-request",
        source=source,
        note="SECOND USER NOTE",
        run_ai=False,
    )
    assert process_inbox(load_config(vault), second.name) == {
        "processed": 1,
        "failed": 0,
        "skipped": 0,
    }
    text = user_note.read_text(encoding="utf-8")
    assert "ORIGINAL USER NOTE" in text
    assert "SECOND USER NOTE" in text
    processed = load_config(vault).path("processed_request_folder") / second.name
    processed_frontmatter, _ = read_note(processed)
    assert processed_frontmatter["status"] == "completed"
    assert processed_frontmatter["result_paper_uid"] == uid
    after_second = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert after_second["job"]["stage"] == "deduplicate"
    assert initial["paper_uid"] == uid

    third = _write_form_flow_request(
        vault,
        request_id="third-request",
        source=source,
        note="THIRD USER NOTE",
        run_ai=False,
    )
    assert process_inbox(load_config(vault), third.name)["processed"] == 1
    final_text = user_note.read_text(encoding="utf-8")
    assert "SECOND USER NOTE" in final_text
    assert "THIRD USER NOTE" in final_text


def test_form_flow_note_survives_ai_failure_and_analyze_retry(
    golden: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = golden["vault"]
    source = "https://arxiv.org/abs/2601.00006"
    uid = "arxiv:2601.00006"
    request = _write_form_flow_request(
        vault,
        request_id="ai-failure-note",
        source=source,
        note="IMPORTANT NOTE",
    )
    monkeypatch.setattr(golden["importer"], "make_provider", lambda *_args: FailingProvider())
    assert process_inbox(load_config(vault), request.name) == {
        "processed": 0,
        "failed": 1,
        "skipped": 0,
    }
    failed = load_config(vault).path("failed_folder") / request.name
    assert failed.is_file()
    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert inspected["job"]["status"] == "failed_retryable"
    assert inspected["ai"]["status"] == "failed"
    assert inspected["pdf"]["exists"] is True
    assert inspected["text"]["exists"] is True
    assert inspected["user_note"]["exists"] is True
    user_note = vault / inspected["user_note"]["path"]
    assert "IMPORTANT NOTE" in user_note.read_text(encoding="utf-8")
    counts_before_retry = dict(golden["counters"])

    monkeypatch.setattr(golden["importer"], "make_provider", golden["make_provider"])
    retried = golden["runner"].invoke(
        app,
        ["paper", "analyze", uid, "--vault", str(vault)],
    )
    assert retried.exit_code == 0, retried.stdout or repr(retried.exception)
    assert golden["counters"] == counts_before_retry
    assert "IMPORTANT NOTE" in user_note.read_text(encoding="utf-8")
    final = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert final["ai"]["status"] == "complete"


def test_form_flow_request_retry_does_not_duplicate_user_note(
    golden: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = golden["vault"]
    source = "https://arxiv.org/abs/2601.00007"
    uid = "arxiv:2601.00007"
    request = _write_form_flow_request(
        vault,
        request_id="retry-idempotency",
        source=source,
        note="DO NOT DUPLICATE",
    )
    monkeypatch.setattr(golden["importer"], "make_provider", lambda *_args: FailingProvider())
    assert process_inbox(load_config(vault), request.name)["failed"] == 1
    config = load_config(vault)
    failed = config.path("failed_folder") / request.name
    retry = config.path("request_folder") / request.name
    failed.replace(retry)
    assert process_inbox(load_config(vault), retry.name)["failed"] == 1

    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    user_note = vault / inspected["user_note"]["path"]
    assert user_note.read_text(encoding="utf-8").count("DO NOT DUPLICATE") == 1


def test_render_failed_analysis_does_not_create_ai_markdown(
    golden: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = golden["vault"]
    source = "https://arxiv.org/abs/2601.00008"
    uid = "arxiv:2601.00008"
    request = _write_form_flow_request(
        vault,
        request_id="failed-render",
        source=source,
        note="PRESERVE BEFORE FAILED RENDER",
    )
    monkeypatch.setattr(golden["importer"], "make_provider", lambda *_args: FailingProvider())
    assert process_inbox(load_config(vault), request.name)["failed"] == 1
    before = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert before["ai"]["status"] == "failed"
    assert before["ai"]["markdown_exists"] is False
    user_note = vault / before["user_note"]["path"]
    user_note_hash = hashlib.sha256(user_note.read_bytes()).hexdigest()

    rendered = golden["runner"].invoke(
        app,
        ["paper", "render", uid, "--vault", str(vault)],
    )
    assert rendered.exit_code == 0, rendered.stdout or repr(rendered.exception)
    after = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert after["paper_hub"]["exists"] is True
    assert after["ai"]["status"] == "failed"
    assert after["ai"]["markdown_exists"] is False
    assert hashlib.sha256(user_note.read_bytes()).hexdigest() == user_note_hash


def test_form_flow_retry_preserves_import_intent(
    golden: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = golden["vault"]
    source = "https://arxiv.org/abs/2601.00009"
    uid = "arxiv:2601.00009"
    request = _write_form_flow_request(
        vault,
        request_id="preserve-import-intent",
        source=source,
        note="PRESERVE COMPLETE IMPORT INTENT",
        topic_hint="Tactile Sensing",
        priority=5,
        queued=True,
        favorite=True,
        user_tags=["golden-tag", "retry-intent"],
    )
    monkeypatch.setattr(
        golden["importer"], "make_provider", lambda *_args: FailingProvider()
    )
    assert process_inbox(load_config(vault), request.name)["failed"] == 1

    record_path = vault / ".paperflow/data/papers/arxiv_2601.00009.json"
    failed_record = json.loads(record_path.read_text(encoding="utf-8"))
    assert failed_record["system_retry_context"] == {
        "import_method": "form-flow",
        "topic_hint": "Tactile Sensing",
    }
    sidecar = load_user_record(vault, failed_record)
    assert sidecar is not None
    assert sidecar.user["user_priority"] == 5
    assert sidecar.user["user_favorite"] is True
    assert sidecar.user["user_reading_status"] == "queued"
    assert sidecar.user["user_added_tags"] == ["golden-tag", "retry-intent"]

    merge_and_save_user_record(vault, failed_record, {"user_rating": 5})
    pdf_path = vault / failed_record["paper_pdf_path"]
    text_path = vault / ".paperflow/cache/arxiv_2601.00009.txt"
    pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    text_hash = hashlib.sha256(text_path.read_bytes()).hexdigest()
    counts_before_retry = dict(golden["counters"])

    monkeypatch.setattr(golden["importer"], "make_provider", golden["make_provider"])
    retried = golden["runner"].invoke(
        app,
        ["paper", "analyze", uid, "--vault", str(vault)],
    )
    assert retried.exit_code == 0, retried.stdout or repr(retried.exception)
    assert golden["counters"] == counts_before_retry
    assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == pdf_hash
    assert hashlib.sha256(text_path.read_bytes()).hexdigest() == text_hash

    final_record = json.loads(record_path.read_text(encoding="utf-8"))
    assert final_record["user_priority"] == 5
    assert final_record["user_favorite"] is True
    assert final_record["user_reading_status"] == "queued"
    assert final_record["user_added_tags"] == ["golden-tag", "retry-intent"]
    assert final_record["user_rating"] == 5
    assert "Tactile Sensing" in final_record["ai_topics"]
    assert final_record["system_import_method"] == "form-flow"
    assert "system_retry_context" not in final_record

    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert inspected["ai"]["status"] == "complete"
    assert inspected["job"]["status"] == "completed"
    user_note = vault / inspected["user_note"]["path"]
    assert "PRESERVE COMPLETE IMPORT INTENT" in user_note.read_text(encoding="utf-8")


def test_duplicate_form_flow_updates_user_projection_without_system_reprocessing(
    golden: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = golden["vault"]
    source = "https://arxiv.org/abs/2601.00010"
    uid = "arxiv:2601.00010"
    ai_calls = {"count": 0}

    def counting_provider(*args, **kwargs):
        ai_calls["count"] += 1
        return golden["make_provider"](*args, **kwargs)

    monkeypatch.setattr(golden["importer"], "make_provider", counting_provider)
    imported = _json(
        golden["runner"].invoke(
            app,
            ["paper", "add", source, "--vault", str(vault)],
        )
    )
    assert imported["status"] == "imported"
    inspected = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    user_note = vault / inspected["user_note"]["path"]
    hub = vault / inspected["paper_hub"]["path"]
    review_result = _json(
        golden["runner"].invoke(
            app,
            ["review", "create", uid, "--vault", str(vault)],
        )
    )
    review = vault / review_result["path"]
    annotation_result = _json(
        golden["runner"].invoke(
            app,
            [
                "annotation",
                "create",
                uid,
                f"[[{inspected['pdf']['path']}#page=1]]",
                "--body",
                "Duplicate projection guard",
                "--apply",
                "--vault",
                str(vault),
            ],
        )
    )
    annotation = vault / annotation_result["markdown"]
    protected_hashes = {
        "user_note": hashlib.sha256(user_note.read_bytes()).hexdigest(),
        "review": hashlib.sha256(review.read_bytes()).hexdigest(),
        "annotation": hashlib.sha256(annotation.read_bytes()).hexdigest(),
    }
    counters_before = dict(golden["counters"])
    ai_before = ai_calls["count"]

    request = _write_form_flow_request(
        vault,
        request_id="duplicate-projection-refresh",
        source=source,
        note="",
        priority=5,
        queued=True,
        favorite=True,
        user_tags=["golden-tag", "projection-fresh"],
    )
    assert process_inbox(load_config(vault), request.name) == {
        "processed": 1,
        "failed": 0,
        "skipped": 0,
    }
    assert golden["counters"] == counters_before
    assert ai_calls["count"] == ai_before

    record_path = vault / ".paperflow/data/papers/arxiv_2601.00010.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    sidecar = load_user_record(vault, record)
    assert sidecar is not None
    for values in (record, sidecar.user, read_note(hub)[0]):
        assert values["user_priority"] == 5
        assert values["user_favorite"] is True
        assert values["user_reading_status"] == "queued"
        assert values["user_added_tags"] == ["golden-tag", "projection-fresh"]

    assert hashlib.sha256(user_note.read_bytes()).hexdigest() == protected_hashes["user_note"]
    assert hashlib.sha256(review.read_bytes()).hexdigest() == protected_hashes["review"]
    assert hashlib.sha256(annotation.read_bytes()).hexdigest() == protected_hashes["annotation"]
    final = _json(
        golden["runner"].invoke(
            app,
            ["paper", "inspect", uid, "--vault", str(vault)],
        )
    )
    assert final["job"]["stage"] == "deduplicate"
    assert final["review"]["exists"] is True
    assert final["annotations"]["count"] == 1
