from __future__ import annotations

import json
import re
from pathlib import Path

from paperflow.annotations.markdown_parser import parse_annotation
from paperflow.annotations.markdown_renderer import render_annotation
from paperflow.annotations.models import Annotation
from paperflow.obsidian.frontmatter import dump_frontmatter, read_note
from paperflow.utils import atomic_json, atomic_write


class AnnotationConflict(RuntimeError):
    pass


INDEX_START = "<!-- PAPERFLOW_ANNOTATION_INDEX_START -->"
INDEX_END = "<!-- PAPERFLOW_ANNOTATION_INDEX_END -->"
LEGACY_SCAFFOLD_LINES = {
    "# 标注",
    "# Annotations",
    "PDF++ 复制的标注链接可粘贴到这里；正式标注由 PaperFlow 命令同步。",
    "PDF++ links can be pasted here; formal annotations are synchronized by PaperFlow.",
}


class AnnotationStore:
    """Markdown is authoritative; JSON is a rebuildable private sidecar."""

    def __init__(self, vault: Path, markdown_root: str, data_root: str):
        self.vault = vault.resolve()
        self.markdown_root = self.vault / markdown_root
        self.data_root = self.vault / data_root

    def paths(self, annotation: Annotation) -> tuple[Path, Path]:
        paper_id = self.paper_id(annotation.paper_uid)
        name = f"{annotation.annotation_id}.annotation"
        return (self.markdown_root / paper_id / f"{name}.md",
                self.data_root / paper_id / f"{name}.json")

    @staticmethod
    def paper_id(paper_uid: str) -> str:
        value = paper_uid.replace(":", "_")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
            raise ValueError("unsafe paper_uid")
        return value

    def index_path(self, paper_uid: str) -> Path:
        return self.markdown_root / self.paper_id(paper_uid) / "index.md"

    def _legacy_indexes(self, paper_uid: str) -> list[Path]:
        paper_id = self.paper_id(paper_uid)
        canonical = self.index_path(paper_uid).resolve()
        return [
            path for path in sorted(self.markdown_root.glob(f"*/{paper_id}/index.md"))
            if path.resolve() != canonical
        ]

    @staticmethod
    def _user_body(body: str) -> str:
        if INDEX_START in body and INDEX_END in body:
            start = body.index(INDEX_START)
            end = body.index(INDEX_END, start) + len(INDEX_END)
            return (body[:start] + body[end:]).strip()
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if lines and all(line in LEGACY_SCAFFOLD_LINES for line in lines):
            return ""
        return body.strip()

    def rebuild_paper_index(
        self, paper_uid: str, annotations: list[Annotation] | None = None,
        *, dry_run: bool = False,
    ) -> dict:
        if annotations is None:
            annotations = []
            seen: set[str] = set()
            for path in sorted(self.markdown_root.rglob("*.annotation.md")):
                annotation, _ = parse_annotation(path)
                if annotation.paper_uid == paper_uid and annotation.annotation_id not in seen:
                    annotations.append(annotation)
                    seen.add(annotation.annotation_id)

        target = self.index_path(paper_uid)
        metadata: dict = {}
        preserved: list[str] = []
        if target.exists():
            metadata, body = read_note(target)
            current = self._user_body(body)
            if current:
                preserved.append(current)

        imported = []
        existing_text = "\n\n".join(preserved)
        for legacy in self._legacy_indexes(paper_uid):
            _, body = read_note(legacy)
            user_body = self._user_body(body)
            marker = f"<!-- PAPERFLOW_IMPORTED_LEGACY_INDEX: {legacy.relative_to(self.vault).as_posix()} -->"
            if user_body and marker not in existing_text:
                imported.append(f"{marker}\n{user_body}")

        entries = []
        for annotation in sorted(annotations, key=lambda item: (item.updated_at, item.annotation_id)):
            markdown, _ = self.paths(annotation)
            anchor = annotation.preferred_revision.anchor
            relative = markdown.relative_to(self.vault).as_posix()
            entries.append(
                f"- [[{relative}|{annotation.kind} · p.{anchor.page}]]"
            )
        generated = "\n".join(entries) or "- 暂无标注 / No annotations yet."
        sections = [item for item in [*preserved, *imported] if item]
        sections.append(f"{INDEX_START}\n# 标注 / Annotations\n\n{generated}\n{INDEX_END}")
        metadata = {
            **metadata,
            "type": "paperflow-annotation-index-note",
            "paper_uid": paper_uid,
            "annotation_count": len(annotations),
        }
        if not dry_run:
            atomic_write(target, dump_frontmatter(metadata) + "\n" + "\n\n".join(sections) + "\n")
        return {
            "paper_uid": paper_uid,
            "path": target.relative_to(self.vault).as_posix(),
            "annotations": len(annotations),
            "legacy_indexes": [
                path.relative_to(self.vault).as_posix()
                for path in self._legacy_indexes(paper_uid)
            ],
            "legacy_user_sections_imported": len(imported),
            "dry_run": dry_run,
        }

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
        by_id: dict[str, Annotation] = {}
        for path in sorted(self.markdown_root.rglob("*.annotation.md")):
            annotation, _ = parse_annotation(path)
            self.save(annotation, dry_run=dry_run)
            by_id[annotation.annotation_id] = annotation
        entries = [
            {
                "annotation_id": annotation.annotation_id,
                "paper_uid": annotation.paper_uid,
                "path": self.paths(annotation)[0].relative_to(self.vault).as_posix(),
                "status": annotation.preferred_revision.status,
            }
            for annotation in sorted(by_id.values(), key=lambda item: item.annotation_id)
        ]
        paper_indexes = []
        paper_uids = sorted({annotation.paper_uid for annotation in by_id.values()})
        for paper_uid in paper_uids:
            paper_indexes.append(self.rebuild_paper_index(
                paper_uid,
                [item for item in by_id.values() if item.paper_uid == paper_uid],
                dry_run=dry_run,
            ))
        index = self.data_root / "index.json"
        if not dry_run:
            atomic_json(index, {
                "type": "paperflow-annotation-index", "schema_version": 1,
                "entries": entries,
            })
        return {
            "dry_run": dry_run, "annotations": len(entries), "entries": entries,
            "paper_indexes": paper_indexes,
        }
