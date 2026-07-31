"""Deterministic Zotero Connector event state machine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperflow.utils import atomic_json, iso_beijing
from paperflow.zotero.store import runtime_root

STATES = {"detected", "waiting_for_metadata", "waiting_for_pdf", "stabilizing", "waiting_for_collection", "waiting_for_identity", "identity_resolved", "queued", "complete", "failed", "ignored"}


class ZoteroEventProcessor:
    def __init__(self, root: Path, *, collection_only: bool = True, collections: list[str] | None = None, require_pdf: bool = True, debounce_seconds: int = 10, auto_queue: bool = True) -> None:
        self.root = root.resolve()
        self.collection_only = collection_only
        self.collections = set(collections or ["PaperFlow"])
        self.require_pdf = require_pdf
        self.debounce_seconds = debounce_seconds
        self.auto_queue = auto_queue

    @property
    def path(self) -> Path:
        return runtime_root(self.root) / "zotero-pipeline-state.json"

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": 1, "items": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "items": {}}
        return value if isinstance(value, dict) else {"schema_version": 1, "items": {}}

    def handle(self, body: dict[str, Any]) -> dict[str, Any]:
        item_key = str(body.get("item_key") or "").strip()
        event = str(body.get("event") or "").strip().casefold()
        if not item_key or not event:
            raise ValueError("item_key and event are required")
        state = self._load()
        items = state.setdefault("items", {})
        previous = items.get(item_key, {}) if isinstance(items.get(item_key), dict) else {}
        if event == "delete":
            current = {**previous, "state": "ignored", "reason": "deleted"}
        elif body.get("item_type") not in {None, "", "regular", "journalArticle", "conferencePaper", "preprint"} or body.get("is_regular") is False:
            current = {**previous, "state": "ignored", "reason": "not-regular-item"}
        elif self.require_pdf and body.get("has_pdf") is not True:
            current = {**previous, "state": "waiting_for_pdf"}
        elif self.require_pdf and body.get("pdf_stable") is not True:
            current = {**previous, "state": "stabilizing"}
        elif self.collection_only and body.get("in_collection") is not True:
            current = {**previous, "state": "waiting_for_collection"}
        elif body.get("identity_resolved") is not True:
            current = {**previous, "state": "waiting_for_identity"}
        else:
            digest = str(body.get("pdf_sha256") or "")
            profile = str(body.get("analysis_profile") or "")
            if body.get("analysis_reusable") is True:
                current = {
                    **previous,
                    "state": "complete",
                    "reason": "canonical-analysis-reused",
                    "pdf_sha256": digest,
                    "analysis_profile": profile,
                }
            elif digest and digest == previous.get("pdf_sha256") and profile and profile == previous.get("analysis_profile"):
                current = {**previous, "state": "complete", "reason": "same-hash-and-profile"}
            else:
                current = {**previous, "state": "queued", "reason": "ready-for-analysis", "pdf_sha256": digest, "analysis_profile": profile, "debounce_seconds": self.debounce_seconds}
        current["updated_at"] = iso_beijing()
        if current.get("state") not in STATES:
            raise ValueError("invalid pipeline state")
        items[item_key] = current
        state["updated_at"] = iso_beijing()
        atomic_json(self.path, state)
        queue_render = (
            current.get("reason") == "canonical-analysis-reused"
            and (
                previous.get("state") != "complete"
                or previous.get("reason") != "canonical-analysis-reused"
                or previous.get("pdf_sha256") != current.get("pdf_sha256")
                or previous.get("analysis_profile") != current.get("analysis_profile")
            )
        )
        return {
            "ok": True,
            "item_key": item_key,
            "state": current["state"],
            "previous_state": previous.get("state", ""),
            "queue_analysis": current["state"] == "queued" and self.auto_queue,
            "queue_render": queue_render,
            "reuse_analysis": current.get("reason") == "canonical-analysis-reused",
            "reason": str(current.get("reason") or ""),
            "state_path": self.path.relative_to(self.root).as_posix(),
        }


__all__ = ["STATES", "ZoteroEventProcessor"]
