from __future__ import annotations

"""Versioned PaperFlow Template Set management with safe import/export."""

import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from paperflow.data.compose import compose_record
from paperflow.obsidian.view_model import build_paper_view_model
from paperflow.workspace import _distribution_resource

REQUIRED = {"manifest.json"}


class TemplateSetError(ValueError):
    pass


class TemplateSetManager:
    def __init__(self, root: Path):
        self.root = root
        self.user_root = root / ".paperflow/templates/sets"
        self.state_path = root / ".paperflow/templates/active.json"
        self.builtin_root = _distribution_resource("templates/sets")

    def _roots(self) -> list[tuple[str, Path, bool]]:
        roots = [("builtin", self.builtin_root, True)]
        if self.user_root.exists():
            roots.append(("user", self.user_root, False))
        return roots

    def _manifest(self, path: Path) -> dict[str, Any]:
        manifest = path / "manifest.json"
        if not manifest.is_file():
            raise TemplateSetError(f"missing manifest: {path}")
        value = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not value.get("id"):
            raise TemplateSetError(f"invalid manifest: {manifest}")
        for relative in value.get("files", []):
            candidate = (path / relative).resolve()
            try:
                candidate.relative_to(path.resolve())
            except ValueError as exc:
                raise TemplateSetError(f"template escapes set root: {relative}") from exc
        return value

    def _find(self, set_id: str) -> tuple[Path, dict[str, Any], bool]:
        wanted = set_id.removeprefix("builtin:").removeprefix("user:")
        if not wanted or wanted in {".", ".."} or "/" in wanted or "\\" in wanted or ".." in PurePosixPath(wanted).parts:
            raise TemplateSetError(f"unsafe template set id: {set_id}")
        for kind, root, readonly in self._roots():
            candidate = root / wanted
            if candidate.is_dir():
                return candidate, self._manifest(candidate), readonly
        raise TemplateSetError(f"unknown template set: {set_id}")

    def list(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for kind, root, readonly in self._roots():
            if not root.exists():
                continue
            for path in sorted(p for p in root.iterdir() if p.is_dir()):
                try:
                    manifest = self._manifest(path)
                except Exception as exc:
                    result.append({"id": path.name, "kind": kind, "valid": False, "error": str(exc)})
                    continue
                result.append({"id": manifest["id"], "kind": kind, "read_only": readonly, **manifest})
        active = self.active_id()
        for item in result:
            item["active"] = item.get("id") == active
        return result

    def active_id(self) -> str:
        if self.state_path.exists():
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return str(value.get("active_set") or "academic-zh")
        return "academic-zh"

    def use(self, set_id: str) -> dict[str, Any]:
        path, manifest, _ = self._find(set_id)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"active_set": manifest["id"], "updated_at": __import__("datetime").datetime.now().isoformat()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"active_set": manifest["id"], "path": path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else str(path), "manifest": manifest}

    def copy(self, set_id: str, destination: str | None = None) -> dict[str, Any]:
        source, manifest, readonly = self._find(set_id)
        name = destination or manifest["id"]
        target = self.user_root / name
        if target.exists():
            raise FileExistsError(target)
        shutil.copytree(source, target)
        return {"copied": manifest["id"], "destination": target.relative_to(self.root).as_posix(), "source_read_only": readonly}

    def validate(self, set_id: str | None = None) -> dict[str, Any]:
        items = [self._find(set_id)[1]] if set_id else self.list()
        errors: list[str] = []
        for item in items:
            if not item.get("valid", True):
                errors.append(str(item.get("error")))
            if item.get("context_version", 1) > 1:
                errors.append(f"{item.get('id')}: unsupported context version")
        return {"ok": not errors, "errors": errors, "sets": items}

    def doctor(self) -> dict[str, Any]:
        result = self.validate()
        result["active_set"] = self.active_id()
        result["user_root"] = self.user_root.relative_to(self.root).as_posix()
        return result

    def preview(self, set_id: str, template_name: str, record: dict[str, Any]) -> str:
        path, _, _ = self._find(set_id)
        env = SandboxedEnvironment(loader=FileSystemLoader(path), undefined=StrictUndefined, autoescape=False)
        template = env.get_template(template_name)
        settings = record.pop("_settings", None)
        if settings is None:
            raise TemplateSetError("preview requires workspace settings")
        return template.render(**build_paper_view_model(self.root, settings, record))

    def diff(self, left: str, right: str) -> dict[str, Any]:
        left_path, left_manifest, _ = self._find(left)
        right_path, right_manifest, _ = self._find(right)
        files = sorted(set(left_manifest.get("files", [])) | set(right_manifest.get("files", [])))
        changed: list[str] = []
        for name in files:
            left_bytes = (left_path / name).read_bytes() if (left_path / name).exists() else None
            right_bytes = (right_path / name).read_bytes() if (right_path / name).exists() else None
            if left_bytes != right_bytes:
                changed.append(name)
        return {"left": left_manifest["id"], "right": right_manifest["id"], "changed_files": changed}

    def export(self, set_id: str, output: Path) -> Path:
        source, _, _ = self._find(set_id)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(source.rglob("*")):
                if file.is_file():
                    archive.write(file, PurePosixPath(source.name, file.relative_to(source).as_posix()).as_posix())
        return output

    def import_zip(self, archive_path: Path, name: str | None = None) -> dict[str, Any]:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > 200 or sum(item.file_size for item in entries) > 10 * 1024 * 1024:
                raise TemplateSetError("template archive is too large")
            target_name = name or Path(entries[0].filename).parts[0]
            target = self.user_root / target_name
            if target.exists():
                raise FileExistsError(target)
            for item in entries:
                parts = PurePosixPath(item.filename).parts
                if not parts or ".." in parts or PurePosixPath(item.filename).is_absolute():
                    raise TemplateSetError(f"unsafe archive path: {item.filename}")
            self.user_root.mkdir(parents=True, exist_ok=True)
            archive.extractall(self.user_root)
        manifest = self._manifest(target)
        return {"imported": manifest["id"], "path": target.relative_to(self.root).as_posix()}
