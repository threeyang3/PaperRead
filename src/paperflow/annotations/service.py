from __future__ import annotations

import uuid
from pathlib import Path

from paperflow.annotations.anchors import parse_pdf_link
from paperflow.annotations.models import Annotation, AnnotationRevision
from paperflow.annotations.store import AnnotationStore
from paperflow.utils import iso_beijing
from paperflow.workspace import WorkspaceSettings


class AnnotationService:
    def __init__(self, vault: Path, settings: WorkspaceSettings, *, dry_run: bool = False):
        self.vault = vault
        self.settings = settings
        self.dry_run = dry_run
        self.store = AnnotationStore(vault, settings.paths.annotation_note.root,
                                     settings.paths.user_annotations.root)

    def create(self, paper_uid: str, pdf_link: str, *, pdf_version: int,
               kind: str, motivation: str, body: str = "",
               tags: list[str] | None = None, selected_text: str = "") -> dict:
        now = iso_beijing()
        anchor = parse_pdf_link(
            pdf_link, vault=self.vault, pdf_version=pdf_version,
            selected_text=selected_text,
        )
        annotation = Annotation(
            annotation_id="ann-" + uuid.uuid4().hex,
            paper_uid=paper_uid, kind=kind, motivation=motivation,
            body=body, tags=tags or [], created_at=now, updated_at=now,
            revisions=[AnnotationRevision(revision=1, anchor=anchor, created_at=now)],
        )
        result = self.store.save(annotation, dry_run=self.dry_run)
        index = self.store.rebuild_index(dry_run=self.dry_run)
        return {**result, "index": index}

    def rebuild_index(self) -> dict:
        return self.store.rebuild_index(dry_run=self.dry_run)
