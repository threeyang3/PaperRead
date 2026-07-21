from __future__ import annotations

import json
from pathlib import Path

from paperflow.annotations.markdown_parser import parse_annotation
from paperflow.annotations.markdown_renderer import render_annotation
from paperflow.annotations.models import Annotation
from paperflow.utils import atomic_json, atomic_write


class AnnotationConflict(RuntimeError):
    pass


class AnnotationStore:
    """Markdown is authoritative; JSON is a rebuildable private sidecar."""

    def __init__(self, vault: Path, markdown_root: str, data_root: str):
        self.vault = vault.resolve()
        self.markdown_root = self.vault / markdown_root
        self.data_root = self.vault / data_root

    def paths(self, annotation: Annotation) -> tuple[Path, Path]:
        paper_id = annotation.paper_uid.replace(":", "_")
        name = f"{annotation.annotation_id}.annotation"
        return (self.markdown_root / paper_id / f"{name}.md",
                self.data_root / paper_id / f"{name}.json")

    def save(self, annotation: Annotation, *, dry_run: bool = False) -> dict:
        markdown, sidecar = self.paths(annotation)
        unknown = ""
        if markdown.exists():
            existing, unknown = parse_annotation(markdown)
            if (sidecar.exists() and sidecar.stat().st_mtime > markdown.stat().st_mtime
                    and json.loads(sidecar.read_text(encoding="utf-8"))
                    != existing.model_dump(mode="json")):
                raise AnnotationConflict(
                    "Markdown/JSON were both modified; Manual Review is required"
                )
        result = {
            "annotation_id": annotation.annotation_id,
            "markdown": markdown.relative_to(self.vault).as_posix(),
            "sidecar": sidecar.relative_to(self.vault).as_posix(),
            "dry_run": dry_run,
        }
        if not dry_run:
            atomic_write(markdown, render_annotation(annotation, unknown))
            atomic_json(sidecar, annotation.model_dump(mode="json"))
        return result

    def rebuild_index(self, *, dry_run: bool = False) -> dict:
        entries = []
        for path in sorted(self.markdown_root.rglob("*.annotation.md")):
            annotation, _ = parse_annotation(path)
            self.save(annotation, dry_run=dry_run)
            entries.append({
                "annotation_id": annotation.annotation_id,
                "paper_uid": annotation.paper_uid,
                "path": path.relative_to(self.vault).as_posix(),
                "status": annotation.preferred_revision.status,
            })
        index = self.data_root / "index.json"
        if not dry_run:
            atomic_json(index, {
                "type": "paperflow-annotation-index", "schema_version": 1,
                "entries": entries,
            })
        return {"dry_run": dry_run, "annotations": len(entries), "entries": entries}
