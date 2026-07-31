from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperflow.paths.templates import safe_component
from paperflow.utils import sha256_file


class PdfResolutionError(RuntimeError):
    pass


_VERSIONED_PDF_NAME = re.compile(r"^v([1-9][0-9]*)\.pdf$", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedPdf:
    paper_uid: str
    version: int
    path: Path
    relative_path: str
    sha256: str
    size: int


def _paper_id(paper_uid: str, record: dict[str, Any] | None) -> str:
    if record:
        value = record.get("paper_arxiv_id") or record.get("source_id")
        if value:
            return safe_component(str(value).replace(":", "_"))
    return safe_component(paper_uid.split(":", 1)[-1].replace(":", "_"))


def _safe_workspace_path(root: Path, value: str) -> Path:
    text = str(value).strip()
    normalized = text.replace("\\", "/")
    parts = normalized.split("/")
    if (
        not text
        or Path(text).is_absolute()
        or normalized.startswith("/")
        or normalized.startswith("//")
        or len(normalized) >= 2
        and normalized[1] == ":"
    ):
        raise PdfResolutionError(f"PDF path must be relative: {value}")
    if ".." in parts:
        raise PdfResolutionError(f"PDF path escapes Workspace: {value}")
    candidate = (root.resolve() / Path(*parts)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise PdfResolutionError(f"PDF path escapes Workspace: {value}") from exc
    return candidate


def _validate_pdf(
    root: Path,
    paper_uid: str,
    version: int,
    path: Path,
    *,
    expected_sha256: str = "",
    expected_size: int | None = None,
) -> ResolvedPdf:
    if path.suffix.casefold() != ".pdf":
        raise PdfResolutionError(f"Resolved file is not a PDF: {path.name}")
    versioned_name = _VERSIONED_PDF_NAME.fullmatch(path.name)
    if versioned_name and int(versioned_name.group(1)) != version:
        raise PdfResolutionError(
            f"PDF filename version does not match requested v{version}: {path.name}"
        )
    if not path.is_file():
        raise PdfResolutionError(f"PDF file is missing: {path}")
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise PdfResolutionError(f"PDF header is invalid: {path.name}")
    size = path.stat().st_size
    if expected_size is not None and int(expected_size) != size:
        raise PdfResolutionError(
            f"PDF size mismatch for {paper_uid} v{version}: expected {expected_size}, got {size}"
        )
    digest = sha256_file(path)
    if expected_sha256 and digest != expected_sha256:
        raise PdfResolutionError(f"PDF SHA-256 mismatch for {paper_uid} v{version}")
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PdfResolutionError(f"PDF path escapes Workspace: {path}") from exc
    return ResolvedPdf(
        paper_uid=paper_uid,
        version=version,
        path=path.resolve(),
        relative_path=relative,
        sha256=digest,
        size=size,
    )


def _index_path(root: Path, paper_uid: str) -> Path:
    return (
        root
        / ".paperflow/data/derived/pdf-index"
        / f"{safe_component(paper_uid.replace(':', '_'))}.json"
    )


def _read_index(root: Path, paper_uid: str) -> dict[str, Any] | None:
    path = _index_path(root, paper_uid)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PdfResolutionError(f"PDF index is invalid: {path}") from exc
    if (
        not isinstance(value, dict)
        or value.get("type") != "paperflow-pdf-index"
        or value.get("paper_uid") != paper_uid
        or not isinstance(value.get("versions"), list)
    ):
        raise PdfResolutionError(f"PDF index identity is invalid: {path}")
    seen_versions: set[int] = set()
    for item in value["versions"]:
        if not isinstance(item, dict):
            raise PdfResolutionError(f"PDF index version entry is invalid: {path}")
        try:
            version = int(item.get("version") or 0)
        except (TypeError, ValueError) as exc:
            raise PdfResolutionError(f"PDF index version entry is invalid: {path}") from exc
        if version < 1:
            raise PdfResolutionError(f"PDF index version entry is invalid: {path}")
        if version in seen_versions:
            raise PdfResolutionError(f"PDF index version {version} is duplicated")
        seen_versions.add(version)
    return value


def _from_index(
    root: Path,
    paper_uid: str,
    index: dict[str, Any],
    version: int,
) -> ResolvedPdf:
    matches = [
        item
        for item in index["versions"]
        if isinstance(item, dict) and int(item.get("version") or 0) == version
    ]
    if len(matches) != 1:
        raise PdfResolutionError(f"PDF index current version {version} is missing or duplicated")
    item = matches[0]
    path = _safe_workspace_path(root, str(item.get("path") or ""))
    return _validate_pdf(
        root,
        paper_uid,
        version,
        path,
        expected_sha256=str(item.get("sha256") or ""),
        expected_size=(int(item["size"]) if item.get("size") is not None else None),
    )


def _modeled_derived_paths(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"paper_pdf_path", "pdf_path", "source_pdf_path"} and item:
                found.append(str(item))
            elif isinstance(item, (dict, list)):
                found.extend(_modeled_derived_paths(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_modeled_derived_paths(item))
    return found


def _fallback_candidates(
    root: Path,
    paper_uid: str,
    record: dict[str, Any] | None,
    version: int,
    *,
    allow_legacy_unversioned: bool,
) -> list[Path]:
    candidates: list[Path] = []
    if record and record.get("paper_pdf_path"):
        candidates.append(_safe_workspace_path(root, str(record["paper_pdf_path"])))
    paper_id = _paper_id(paper_uid, record)
    derived = root / ".paperflow/data/derived" / f"{paper_id}.json"
    if derived.is_file():
        try:
            value = json.loads(derived.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PdfResolutionError(f"Derived PDF record is invalid: {derived}") from exc
        for relative in _modeled_derived_paths(value):
            candidates.append(_safe_workspace_path(root, relative))
    year = str((record or {}).get("paper_year") or "")
    if year:
        candidates.extend(
            [
                root / "80 Attachments/Papers" / year / paper_id / f"v{version}.pdf",
                root / "80 Attachments/Papers" / year / f"{paper_id}.pdf",
            ]
        )
    candidates.extend(
        [
            root / "80 Attachments/Papers" / paper_id / f"v{version}.pdf",
            root / "80 Attachments/Papers" / f"{paper_id}.pdf",
            root / "documents/zotero" / f"{paper_id}.pdf",
        ]
    )
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        versioned_name = _VERSIONED_PDF_NAME.fullmatch(resolved.name)
        version_matches = bool(versioned_name and int(versioned_name.group(1)) == version)
        legacy_allowed = versioned_name is None and allow_legacy_unversioned
        if resolved not in unique and resolved.is_file() and (version_matches or legacy_allowed):
            unique.append(resolved)
    return unique


def resolve_pdf_version(
    root: Path,
    paper_uid: str,
    version: int,
    record: dict[str, Any] | None = None,
    *,
    allow_legacy_unversioned: bool = False,
) -> ResolvedPdf:
    if version < 1:
        raise PdfResolutionError("PDF version must be positive")
    index = _read_index(root, paper_uid)
    if index is not None:
        return _from_index(root, paper_uid, index, version)
    candidates = _fallback_candidates(
        root,
        paper_uid,
        record,
        version,
        allow_legacy_unversioned=allow_legacy_unversioned,
    )
    if len(candidates) != 1:
        raise PdfResolutionError(
            f"Expected exactly one modeled PDF for {paper_uid} v{version}; found {len(candidates)}"
        )
    return _validate_pdf(root, paper_uid, version, candidates[0])


def resolve_current_pdf(
    root: Path,
    paper_uid: str,
    record: dict[str, Any] | None = None,
) -> ResolvedPdf:
    index = _read_index(root, paper_uid)
    if index is not None:
        version = int(index.get("current_version") or 0)
        if version < 1:
            raise PdfResolutionError("PDF index current version is invalid")
        return _from_index(root, paper_uid, index, version)
    version = int((record or {}).get("paper_arxiv_version") or 1)
    return resolve_pdf_version(
        root,
        paper_uid,
        version,
        record,
        allow_legacy_unversioned=True,
    )
