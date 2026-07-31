from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from paperflow.ai.chatgpt_web_adapter import ChatGPTWebAdapter
from paperflow.models import PaperMetadata
from paperflow.pdf_resolver import (
    PdfResolutionError,
    resolve_current_pdf,
    resolve_pdf_version,
)


UID = "arxiv:2607.30001"


def _pdf(path: Path, body: bytes) -> str:
    payload = b"%PDF-1.7\n" + body + b"\n%%EOF\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _index(root: Path, *, current: int, versions: list[dict[str, object]]) -> None:
    path = root / ".paperflow/data/derived/pdf-index/arxiv_2607.30001.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "type": "paperflow-pdf-index",
                "schema_version": 1,
                "paper_uid": UID,
                "current_version": current,
                "versions": versions,
            }
        ),
        encoding="utf-8",
    )


def test_chatgpt_web_resolves_workspace_v3_pdf(tmp_path: Path) -> None:
    path = tmp_path / "80 Attachments/Papers/2026/2607.30001/v2.pdf"
    digest = _pdf(path, b"current")
    _index(
        tmp_path,
        current=2,
        versions=[
            {
                "version": 2,
                "path": path.relative_to(tmp_path).as_posix(),
                "sha256": digest,
                "size": path.stat().st_size,
            }
        ],
    )
    metadata = PaperMetadata(
        paper_uid=UID,
        paper_arxiv_id="2607.30001",
        paper_arxiv_version=2,
        paper_title="Resolver",
    )

    assert ChatGPTWebAdapter(tmp_path)._paper_pdf(metadata) == path


def test_pdf_resolver_uses_current_pdf_index_version(tmp_path: Path) -> None:
    first = tmp_path / "80 Attachments/Papers/2026/2607.30001/v1.pdf"
    second = tmp_path / "80 Attachments/Papers/2026/2607.30001/v2.pdf"
    first_hash = _pdf(first, b"v1")
    second_hash = _pdf(second, b"v2")
    _index(
        tmp_path,
        current=2,
        versions=[
            {
                "version": 1,
                "path": first.relative_to(tmp_path).as_posix(),
                "sha256": first_hash,
                "size": first.stat().st_size,
            },
            {
                "version": 2,
                "path": second.relative_to(tmp_path).as_posix(),
                "sha256": second_hash,
                "size": second.stat().st_size,
            },
        ],
    )

    resolved = resolve_current_pdf(tmp_path, UID)

    assert resolved.version == 2
    assert resolved.path == second
    assert resolve_pdf_version(tmp_path, UID, 1).path == first


def test_pdf_resolver_rejects_pdf_hash_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "80 Attachments/Papers/2026/2607.30001/v1.pdf"
    _pdf(path, b"tampered")
    _index(
        tmp_path,
        current=1,
        versions=[
            {
                "version": 1,
                "path": path.relative_to(tmp_path).as_posix(),
                "sha256": "0" * 64,
                "size": path.stat().st_size,
            }
        ],
    )

    with pytest.raises(PdfResolutionError, match="SHA-256"):
        resolve_current_pdf(tmp_path, UID)


def test_pdf_resolver_does_not_choose_first_recursive_match(tmp_path: Path) -> None:
    _pdf(tmp_path / "80 Attachments/Papers/1999/decoy/2607.30001.pdf", b"decoy")
    current = tmp_path / "80 Attachments/Papers/2026/2607.30001/v3.pdf"
    digest = _pdf(current, b"current")
    _index(
        tmp_path,
        current=3,
        versions=[
            {
                "version": 3,
                "path": current.relative_to(tmp_path).as_posix(),
                "sha256": digest,
                "size": current.stat().st_size,
            }
        ],
    )

    assert resolve_current_pdf(tmp_path, UID).path == current


def test_pdf_resolver_supports_legacy_workspace_path(tmp_path: Path) -> None:
    legacy = tmp_path / "80 Attachments/Papers/2026/2607.30001.pdf"
    digest = _pdf(legacy, b"legacy")

    resolved = resolve_current_pdf(
        tmp_path,
        UID,
        record={
            "paper_uid": UID,
            "paper_year": 2026,
            "paper_arxiv_version": 1,
            "paper_pdf_path": legacy.relative_to(tmp_path).as_posix(),
        },
    )

    assert resolved.path == legacy
    assert resolved.sha256 == digest


def test_pdf_resolver_rejects_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.pdf"
    digest = _pdf(outside, b"outside")
    _index(
        tmp_path,
        current=1,
        versions=[
            {
                "version": 1,
                "path": "../outside.pdf",
                "sha256": digest,
                "size": outside.stat().st_size,
            }
        ],
    )

    with pytest.raises(PdfResolutionError, match="escapes"):
        resolve_current_pdf(tmp_path, UID)


def test_pdf_resolver_rejects_missing_index_entry(tmp_path: Path) -> None:
    _index(tmp_path, current=2, versions=[])

    with pytest.raises(PdfResolutionError, match="current version"):
        resolve_current_pdf(tmp_path, UID)
