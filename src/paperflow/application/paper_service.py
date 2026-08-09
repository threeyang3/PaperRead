from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperflow.config import ensure_layout, load_config
from paperflow.database import Database
from paperflow.locking import FileLock
from paperflow.obsidian.artifacts import artifact_path
from paperflow.obsidian.frontmatter import read_note
from paperflow.pipeline.analyze import analyze_uid
from paperflow.pipeline.import_paper import import_paper
from paperflow.pipeline.render import render_uid
from paperflow.utils import safe_slug


class PaperApplicationService:
    """Stable core-paper operations for CLI and future UI adapters.

    Existing pipeline functions remain the implementation boundary.  This
    service only centralizes Vault resolution, locking, and result assembly so
    user interfaces cannot silently grow independent workflow variants.
    """

    def __init__(self, vault: Path | None = None):
        self.config = load_config(vault)
        ensure_layout(self.config)

    def _record_path(self, paper_uid: str) -> Path:
        return (
            self.config.root
            / ".paperflow/data/papers"
            / f"{safe_slug(paper_uid)}.json"
        )

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
        with FileLock(self.config.root / ".paperflow/runtime/pipeline.lock"):
            return import_paper(
                self.config,
                source,
                priority=priority,
                topic=topic,
                run_ai=run_ai,
                force=force_refresh,
                provider=provider,
            )

    def analyze_paper(
        self,
        paper_uid: str,
        *,
        provider: str | None = None,
    ) -> dict[str, Any]:
        with FileLock(self.config.root / ".paperflow/runtime/pipeline.lock"):
            return analyze_uid(self.config, paper_uid, provider)

    def refresh_paper(self, paper_uid: str) -> dict[str, Any]:
        record = json.loads(
            self._record_path(paper_uid).read_text(encoding="utf-8")
        )
        source = record.get("paper_abs_url") or record.get("paper_pdf_url")
        if not source:
            raise ValueError(f"Paper {paper_uid} has no refreshable source URL")
        with FileLock(self.config.root / ".paperflow/runtime/pipeline.lock"):
            return import_paper(self.config, source, force=True)

    def render_paper(self, paper_uid: str) -> Path:
        with FileLock(self.config.root / ".paperflow/runtime/pipeline.lock"):
            return render_uid(self.config, paper_uid)

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
        text_path = (
            self.config.root
            / ".paperflow/cache"
            / f"{safe_slug(canonical_uid)}.txt"
        )
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
            review_root = (
                self.config.root / self.config.workspace.paths.paper_review.root
            )
            candidates = (
                sorted(review_root.rglob("*.review.md"))
                if review_root.exists()
                else []
            )
            for candidate in candidates:
                try:
                    frontmatter, _ = read_note(candidate)
                except Exception:
                    continue
                if str(frontmatter.get("paper_uid") or "") == canonical_uid:
                    review_info = {
                        "exists": True,
                        "path": candidate.relative_to(
                            self.config.root
                        ).as_posix(),
                        "review_id": str(frontmatter.get("review_id") or ""),
                    }
                    break
            annotation_root = (
                self.config.root / self.config.workspace.paths.annotation_note.root
            )
            candidates = (
                annotation_root.rglob("*.annotation.md")
                if annotation_root.exists()
                else []
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
            self.config.path("manual_review_folder")
            / f"{safe_slug(canonical_uid)}-topics.md"
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
                    hashlib.sha256(
                        (self.config.root / pdf_path).read_bytes()
                    ).hexdigest()
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
