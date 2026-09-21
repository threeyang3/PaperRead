from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperflow.config import Config, ensure_layout, load_config
from paperflow.data.user_store import (
    merge_user_data,
    merge_user_values,
    save_user_record,
)
from paperflow.database import Database
from paperflow.locking import FileLock
from paperflow.obsidian.artifacts import artifact_path
from paperflow.obsidian.frontmatter import read_note, write_note
from paperflow.pipeline.analyze import analyze_uid
from paperflow.pipeline.import_paper import ImportUserIntent, import_paper
from paperflow.pipeline.render import render_uid
from paperflow.utils import atomic_json, safe_slug


@dataclass(frozen=True)
class AddPaperRequest:
    """Application input shared by CLI and request-driven adapters."""

    source: str
    run_ai: bool = True
    topic_hint: str | None = None
    priority: int | None = None
    favorite: bool | None = None
    queued: bool | None = None
    user_tags: tuple[str, ...] | None = None
    user_note: str | None = None
    source_request_id: str | None = None
    import_method: str = "manual"
    force_refresh: bool = False
    provider: str | None = None

    def import_intent(self) -> ImportUserIntent | None:
        # CLI defaults describe a new import but are not durable user updates
        # for a duplicate. Request-driven adapters explicitly identify their
        # source so defaults and user intent cannot be confused.
        if self.import_method != "form-flow" and self.source_request_id is None:
            return None
        return ImportUserIntent(
            priority=self.priority if self.priority is not None else 3,
            favorite=self.favorite if self.favorite is not None else False,
            queued=self.queued if self.queued is not None else False,
            user_tags=self.user_tags or (),
            topic_hint=self.topic_hint or "",
            source=self.import_method,
        )


@dataclass(frozen=True)
class OperationResult:
    """Small, adapter-neutral result for a completed paper operation."""

    status: str
    paper_uid: str
    stage: str = ""
    message: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "status": self.status,
            "paper_uid": self.paper_uid,
        }
        if self.stage:
            value["stage"] = self.stage
        if self.message:
            value["message"] = self.message
        value.update(self.artifacts)
        if self.warnings:
            value["warnings"] = list(self.warnings)
        if self.retryable:
            value["retryable"] = True
        return value


class PaperApplicationService:
    """Stable core-paper operations for CLI and future UI adapters.

    Existing pipeline functions remain the implementation boundary.  This
    service only centralizes Vault resolution, locking, and result assembly so
    user interfaces cannot silently grow independent workflow variants.
    """

    def __init__(
        self,
        vault: Path | None = None,
        *,
        config: Config | None = None,
    ):
        self.config = config or load_config(vault)
        ensure_layout(self.config)

    def _record_path(self, paper_uid: str) -> Path:
        return self.config.root / ".paperflow/data/papers" / f"{safe_slug(paper_uid)}.json"

    def _operation_result(self, payload: dict[str, Any]) -> OperationResult:
        paper_uid = str(payload.get("paper_uid") or "")
        db = Database(self.config.root / ".paperflow/state/paperflow.db")
        try:
            job = db.latest_import_job(paper_uid) if paper_uid else None
        finally:
            db.close()
        artifacts = {
            key: value for key, value in payload.items() if key not in {"status", "paper_uid"}
        }
        return OperationResult(
            status=str(payload.get("status") or "completed"),
            paper_uid=paper_uid,
            stage=str((job or {}).get("stage") or ""),
            artifacts=artifacts,
            retryable=str((job or {}).get("status") or "") == "failed_retryable",
        )

    def _refresh_user_projection(
        self,
        paper_uid: str,
        intent: ImportUserIntent,
    ) -> bool:
        record_path = self._record_path(paper_uid)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        note_value = str(record.get("note_path") or "").strip()
        note_path = self.config.root / note_value if note_value else None
        frontmatter: dict[str, Any] = {}
        body = ""
        if note_path and note_path.is_file():
            frontmatter, body = read_note(note_path)
        merged = merge_user_values(
            merge_user_data(self.config.root, record, frontmatter),
            intent.user_values(),
        )
        save_user_record(self.config.root, record, merged)
        record.update(merged)
        atomic_json(record_path, record)
        if note_path and note_path.is_file():
            refreshed_frontmatter = dict(frontmatter)
            refreshed_frontmatter.update(merged)
            write_note(note_path, refreshed_frontmatter, body)
        db = Database(self.config.root / ".paperflow/state/paperflow.db")
        try:
            db.upsert_paper(record)
        finally:
            db.close()
        return bool(note_path and note_path.is_file())

    def add(self, request: AddPaperRequest) -> OperationResult:
        intent = request.import_intent()
        with FileLock(self.config.root / ".paperflow/runtime/pipeline.lock"):
            payload = import_paper(
                self.config,
                request.source,
                priority=request.priority if request.priority is not None else 3,
                topic=request.topic_hint or "",
                run_ai=request.run_ai,
                force=request.force_refresh,
                favorite=request.favorite if request.favorite is not None else False,
                queued=request.queued if request.queued is not None else False,
                user_tags=list(request.user_tags or ()),
                user_note=request.user_note or "",
                user_note_source_id=request.source_request_id,
                import_method=request.import_method,
                provider=request.provider,
                user_intent=intent,
            )
            if payload.get("status") == "skipped" and intent is not None:
                payload["system_work"] = "skipped"
                payload["user_state_updated"] = True
                payload["projection_refreshed"] = self._refresh_user_projection(
                    str(payload["paper_uid"]),
                    intent,
                )
        return self._operation_result(payload)

    def add_paper(
        self,
        source: str,
        *,
        priority: int = 3,
        topic: str = "",
        run_ai: bool = True,
        force_refresh: bool = False,
        provider: str | None = None,
    ) -> dict[str, Any]:
        return self.add(
            AddPaperRequest(
                source=source,
                priority=priority,
                topic_hint=topic,
                run_ai=run_ai,
                force_refresh=force_refresh,
                provider=provider,
            )
        ).to_dict()

    def analyze(
        self,
        paper_uid: str,
        *,
        provider: str | None = None,
    ) -> OperationResult:
        with FileLock(self.config.root / ".paperflow/runtime/pipeline.lock"):
            payload = analyze_uid(self.config, paper_uid, provider)
        return self._operation_result(payload)

    def analyze_paper(
        self,
        paper_uid: str,
        *,
        provider: str | None = None,
    ) -> dict[str, Any]:
        return self.analyze(paper_uid, provider=provider).to_dict()

    def refresh(self, paper_uid: str) -> OperationResult:
        record = json.loads(self._record_path(paper_uid).read_text(encoding="utf-8"))
        source = record.get("paper_abs_url") or record.get("paper_pdf_url")
        if not source:
            raise ValueError(f"Paper {paper_uid} has no refreshable source URL")
        with FileLock(self.config.root / ".paperflow/runtime/pipeline.lock"):
            payload = import_paper(self.config, source, force=True)
        return self._operation_result(payload)

    def refresh_paper(self, paper_uid: str) -> dict[str, Any]:
        return self.refresh(paper_uid).to_dict()

    def render(self, paper_uid: str) -> OperationResult:
        with FileLock(self.config.root / ".paperflow/runtime/pipeline.lock"):
            note_path = render_uid(self.config, paper_uid)
        return OperationResult(
            status="completed",
            paper_uid=paper_uid,
            stage="render",
            artifacts={"note_path": str(note_path)},
        )

    def render_paper(self, paper_uid: str) -> Path:
        return Path(str(self.render(paper_uid).artifacts["note_path"]))

    def inspect(self, paper_uid: str) -> dict[str, Any]:
        return self.inspect_paper(paper_uid)

    def inspect_paper(self, paper_uid: str) -> dict[str, Any]:
        record_path = self._record_path(paper_uid)
        if not record_path.exists():
            return {"paper_uid": paper_uid, "exists": False}
        record = json.loads(record_path.read_text(encoding="utf-8"))
        canonical_uid = str(record.get("paper_uid") or paper_uid)

        def artifact(relative: str | None) -> tuple[bool, str]:
            value = str(relative or "").strip()
            path = self.config.root / value if value else None
            return bool(path and path.is_file()), value

        layer_paths = record.get("layer_paths") or {}
        raw_exists, raw_path = artifact(layer_paths.get("raw"))
        pdf_exists, pdf_path = artifact(record.get("paper_pdf_path"))
        note_exists, note_path = artifact(record.get("note_path"))
        text_path = self.config.root / ".paperflow/cache" / f"{safe_slug(canonical_uid)}.txt"
        ai_record_exists, ai_record_path = artifact(layer_paths.get("ai"))

        ai_note_exists = False
        ai_note_path = ""
        user_note_exists = False
        user_note_path = ""
        review_info: dict[str, Any] = {"exists": False}
        annotation_count = 0
        if self.config.workspace is not None:
            ai_note = artifact_path(
                self.config.root,
                self.config.workspace,
                record,
                "ai_analysis_note",
            )
            user_note = artifact_path(
                self.config.root,
                self.config.workspace,
                record,
                "user_note",
            )
            ai_note_exists = ai_note.is_file()
            ai_note_path = ai_note.relative_to(self.config.root).as_posix()
            user_note_exists = user_note.is_file()
            user_note_path = user_note.relative_to(self.config.root).as_posix()
            review_root = self.config.root / self.config.workspace.paths.paper_review.root
            candidates = sorted(review_root.rglob("*.review.md")) if review_root.exists() else []
            for candidate in candidates:
                try:
                    frontmatter, _ = read_note(candidate)
                except Exception:
                    continue
                if str(frontmatter.get("paper_uid") or "") == canonical_uid:
                    review_info = {
                        "exists": True,
                        "path": candidate.relative_to(self.config.root).as_posix(),
                        "review_id": str(frontmatter.get("review_id") or ""),
                    }
                    break
            annotation_root = self.config.root / self.config.workspace.paths.annotation_note.root
            candidates = (
                annotation_root.rglob("*.annotation.md") if annotation_root.exists() else []
            )
            for candidate in candidates:
                try:
                    frontmatter, _ = read_note(candidate)
                except Exception:
                    continue
                if str(frontmatter.get("paper_uid") or "") == canonical_uid:
                    annotation_count += 1

        reasons: list[str] = []
        topic_review = (
            self.config.path("manual_review_folder") / f"{safe_slug(canonical_uid)}-topics.md"
        )
        if topic_review.exists():
            reasons.append("unmatched-topic")
        if not pdf_exists:
            reasons.append("missing-pdf")
        if record.get("system_requires_manual_review") and not reasons:
            reasons.append("unspecified")

        db = Database(self.config.root / ".paperflow/state/paperflow.db")
        try:
            latest_job = db.latest_import_job(canonical_uid)
        finally:
            db.close()
        return {
            "paper_uid": canonical_uid,
            "exists": True,
            "raw": {"exists": raw_exists, "path": raw_path},
            "pdf": {
                "exists": pdf_exists,
                "path": pdf_path,
                "sha256": (
                    hashlib.sha256((self.config.root / pdf_path).read_bytes()).hexdigest()
                    if pdf_exists
                    else ""
                ),
            },
            "text": {
                "exists": text_path.is_file(),
                "path": text_path.relative_to(self.config.root).as_posix(),
            },
            "ai": {
                "exists": ai_record_exists,
                "path": ai_record_path,
                "markdown_exists": ai_note_exists,
                "markdown_path": ai_note_path,
                "provider": record.get("ai_analysis_provider", ""),
                "model": record.get("ai_analysis_model", ""),
                "analyzed_at": record.get("ai_analyzed_at"),
                "status": record.get("ai_analysis_status", "pending"),
            },
            "paper_hub": {"exists": note_exists, "path": note_path},
            "user_note": {
                "exists": user_note_exists,
                "path": user_note_path,
            },
            "review": review_info,
            "annotations": {"count": annotation_count},
            "manual_review": {
                "required": bool(record.get("system_requires_manual_review")),
                "reasons": reasons,
            },
            "job": latest_job,
        }
