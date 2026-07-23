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
    assert complete["state"] == "complete"


def test_connector_event_ignores_non_regular_and_delete(tmp_path: Path) -> None:
    processor = ZoteroEventProcessor(tmp_path)
    assert processor.handle({"item_key": "PARENT1", "event": "add"})["state"] == "waiting_for_pdf"
    assert processor.handle({"item_key": "NOTE1", "event": "add", "item_type": "note"})["state"] == "ignored"
    assert processor.handle({"item_key": "NOTE1", "event": "delete"})["state"] == "ignored"
