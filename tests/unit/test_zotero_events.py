from __future__ import annotations

from pathlib import Path

from paperflow.zotero.events import ZoteroEventProcessor


def test_connector_event_state_machine_waits_for_pdf_and_collection(tmp_path: Path) -> None:
    processor = ZoteroEventProcessor(tmp_path)
    waiting_pdf = processor.handle({"item_key": "ABCD1234", "event": "add", "has_pdf": False})
    assert waiting_pdf["state"] == "waiting_for_pdf"
    waiting_collection = processor.handle({"item_key": "ABCD1234", "event": "modify", "has_pdf": True, "pdf_stable": True, "in_collection": False})
    assert waiting_collection["state"] == "waiting_for_collection"
    queued = processor.handle({"item_key": "ABCD1234", "event": "modify", "has_pdf": True, "pdf_stable": True, "in_collection": True, "identity_resolved": True, "pdf_sha256": "a" * 64, "analysis_profile": "full_analysis"})
    assert queued["state"] == "queued"
    complete = processor.handle({"item_key": "ABCD1234", "event": "modify", "has_pdf": True, "pdf_stable": True, "in_collection": True, "identity_resolved": True, "pdf_sha256": "a" * 64, "analysis_profile": "full_analysis"})
    assert complete["state"] == "queued"
    assert complete["reason"] == "already-queued"
    assert complete["queue_analysis"] is False


def test_connector_event_ignores_non_regular_and_delete(tmp_path: Path) -> None:
    processor = ZoteroEventProcessor(tmp_path)
    assert processor.handle({"item_key": "PARENT1", "event": "add"})["state"] == "waiting_for_pdf"
    assert processor.handle({"item_key": "NOTE1", "event": "add", "item_type": "note"})["state"] == "ignored"
    assert processor.handle({"item_key": "NOTE1", "event": "delete"})["state"] == "ignored"


def test_connector_event_reuses_canonical_analysis_once(tmp_path: Path) -> None:
    processor = ZoteroEventProcessor(tmp_path)
    body = {
        "item_key": "ABCD1234",
        "event": "modify",
        "has_pdf": True,
        "pdf_stable": True,
        "in_collection": True,
        "identity_resolved": True,
        "pdf_sha256": "b" * 64,
        "analysis_profile": "full_analysis",
        "analysis_reusable": True,
    }
    first = processor.handle(body)
    assert first["state"] == "complete"
    assert first["reuse_analysis"] is True
    assert first["queue_analysis"] is False
    assert first["queue_render"] is True
    second = processor.handle(body)
    assert second["state"] == "complete"
    assert second["queue_render"] is False


def test_canonical_reuse_renders_after_same_hash_pipeline_completion(tmp_path: Path) -> None:
    processor = ZoteroEventProcessor(tmp_path)
    base = {
        "item_key": "ABCD1234",
        "event": "modify",
        "has_pdf": True,
        "pdf_stable": True,
        "in_collection": True,
        "identity_resolved": True,
        "pdf_sha256": "c" * 64,
        "analysis_profile": "full_analysis",
    }
    assert processor.handle(base)["state"] == "queued"
    assert processor.handle(base)["reason"] == "already-queued"
    recovered = processor.handle({**base, "analysis_reusable": True})
    assert recovered["reason"] == "canonical-analysis-reused"
    assert recovered["queue_render"] is True

def test_same_identity_after_failed_event_is_not_falsely_complete(tmp_path: Path) -> None:
    processor = ZoteroEventProcessor(tmp_path)
    event = {
        "item_key": "RETRY123",
        "event": "modify",
        "has_pdf": True, "pdf_stable": True, "in_collection": True,
        "identity_resolved": True, "pdf_sha256": "a" * 64,
        "analysis_profile": "full_analysis",
    }
    first = processor.handle(event)
    assert first["queue_analysis"] is True
    duplicate = processor.handle(event)
    assert duplicate["state"] == "queued"
    assert duplicate["queue_analysis"] is False
    # An explicit canonical-reuse signal, not an identical event, may finish.
    final = processor.handle({**event, "analysis_reusable": True})
    assert final["state"] == "complete"
    assert final["queue_render"] is True
